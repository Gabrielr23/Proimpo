from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    is_workcenter_compatible = fields.Boolean(
        string='Centro Compatible',
        compute='_compute_workcenter_compatible',
        store=False
    )

    workcenter_compatibility_warning = fields.Char(
        string='Advertencia de Compatibilidad',
        compute='_compute_workcenter_compatible',
        store=False
    )

    @api.depends('workcenter_id', 'production_id.product_id')
    def _compute_workcenter_compatible(self):
        """Calcular compatibilidad del centro de trabajo"""
        for workorder in self:
            if workorder.workcenter_id and workorder.production_id and workorder.production_id.product_id:
                incompatible = workorder.production_id.product_id._get_incompatible_workcenters()
                is_compatible = workorder.workcenter_id not in incompatible
                workorder.is_workcenter_compatible = is_compatible
                if not is_compatible:
                    workorder.workcenter_compatibility_warning = _(
                        'ADVERTENCIA: Este centro de trabajo no es compatible con el producto %s'
                    ) % workorder.production_id.product_id.name
                else:
                    workorder.workcenter_compatibility_warning = ''
            else:
                workorder.is_workcenter_compatible = True
                workorder.workcenter_compatibility_warning = ''

    @api.constrains('workcenter_id', 'production_id')
    def _check_workcenter_product_compatibility(self):
        """Prevenir asignación de centros incompatibles"""
        for workorder in self:
            if workorder.workcenter_id and workorder.production_id and workorder.production_id.product_id:
                if not workorder.workcenter_id.is_compatible_with_product(
                    workorder.production_id.product_id
                ):
                    raise ValidationError(_(
                        'Centro de trabajo "%(wc)s" incompatible con producto "%(prod)s".\n'
                        'Seleccione un centro de trabajo diferente.',
                        wc=workorder.workcenter_id.name,
                        prod=workorder.production_id.product_id.name
                    ))

    @api.onchange('workcenter_id')
    def _onchange_workcenter_id(self):
        """Mostrar advertencia en tiempo real al cambiar centro de trabajo"""
        if self.workcenter_id and self.production_id and self.production_id.product_id:
            incompatible = self.production_id.product_id._get_incompatible_workcenters()
            if self.workcenter_id in incompatible:
                return {
                    'warning': {
                        'title': _('Centro de Trabajo Incompatible'),
                        'message': _(
                            'Centro "%(wc)s" marcado incompatible con "%(prod)s".\n'
                            'No podrá guardar con este centro.',
                            wc=self.workcenter_id.name,
                            prod=self.production_id.product_id.name
                        )
                    }
                }

    def _get_alternative_workcenters(self):
        """Obtener centros de trabajo alternativos compatibles"""
        self.ensure_one()
        if not self.operation_id:
            return self.env['mrp.workcenter']

        alternative_workcenters = self.operation_id.workcenter_id | self.operation_id.alternative_workcenter_ids

        if self.production_id and self.production_id.product_id:
            incompatible_workcenters = self.production_id.product_id._get_incompatible_workcenters()
            compatible_workcenters = alternative_workcenters - incompatible_workcenters
        else:
            compatible_workcenters = alternative_workcenters

        return compatible_workcenters
