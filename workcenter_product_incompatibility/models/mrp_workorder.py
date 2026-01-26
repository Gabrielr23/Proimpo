from odoo import models, api, fields, _
from odoo.exceptions import UserError, ValidationError

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'
    
    is_workcenter_compatible = fields.Boolean(
        string='Centro Compatible',
        compute='_compute_workcenter_compatible',
        store=True
    )
    
    workcenter_compatibility_warning = fields.Char(
        string='Advertencia de Compatibilidad',
        compute='_compute_workcenter_compatible',
        store=True
    )
    
    @api.depends('workcenter_id', 'production_id.product_id')
    def _compute_workcenter_compatible(self):
        for workorder in self:
            if workorder.workcenter_id and workorder.production_id.product_id:
                incompatible = workorder.production_id.product_id._get_incompatible_workcenters()
                if workorder.workcenter_id in incompatible:
                    workorder.is_workcenter_compatible = False
                    workorder.workcenter_compatibility_warning = _(
                        'ADVERTENCIA: Este centro de trabajo no es compatible con el producto %s'
                    ) % workorder.production_id.product_id.name
                else:
                    workorder.is_workcenter_compatible = True
                    workorder.workcenter_compatibility_warning = False
            else:
                workorder.is_workcenter_compatible = True
                workorder.workcenter_compatibility_warning = False
    
    @api.constrains('workcenter_id', 'production_id')
    def _check_workcenter_product_compatibility(self):
        """Prevenir asignación de centros incompatibles"""
        for workorder in self:
            if workorder.workcenter_id and workorder.production_id.product_id:
                if not workorder.workcenter_id.is_compatible_with_product(
                    workorder.production_id.product_id
                ):
                    raise ValidationError(_(
                        'No se puede asignar el centro de trabajo "%s" porque es incompatible '
                        'con el producto "%s".\n\n'
                        'Por favor, seleccione un centro de trabajo diferente.'
                    ) % (workorder.workcenter_id.name, workorder.production_id.product_id.name))
    
    @api.onchange('workcenter_id')
    def _onchange_workcenter_id(self):
        """Mostrar advertencia en tiempo real al cambiar centro de trabajo"""
        if self.workcenter_id and self.production_id.product_id:
            incompatible = self.production_id.product_id._get_incompatible_workcenters()
            if self.workcenter_id in incompatible:
                return {
                    'warning': {
                        'title': _('Centro de Trabajo Incompatible'),
                        'message': _(
                            'El centro de trabajo "%s" está marcado como incompatible '
                            'con el producto "%s".\n\n'
                            'No podrá guardar esta orden de trabajo con este centro.'
                        ) % (self.workcenter_id.name, self.production_id.product_id.name)
                    }
                }
    
    def _get_alternative_workcenters(self):
        """Obtener centros de trabajo alternativos compatibles"""
        self.ensure_one()
        if not self.operation_id:
            return self.env['mrp.workcenter']
        
        # Obtener todos los centros alternativos de la operación
        alternative_workcenters = self.operation_id.workcenter_id | self.operation_id.alternative_workcenter_ids
        
        # Filtrar los incompatibles
        incompatible_workcenters = self.production_id.product_id._get_incompatible_workcenters()
        compatible_workcenters = alternative_workcenters - incompatible_workcenters
        
        return compatible_workcenters
