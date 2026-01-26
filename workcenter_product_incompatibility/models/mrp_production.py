from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    @api.constrains('product_id', 'workorder_ids')
    def _check_workcenter_compatibility(self):
        """Validar que no se asignen centros incompatibles"""
        for production in self:
            if production.product_id:
                incompatible_workcenters = production.product_id._get_incompatible_workcenters()
                for workorder in production.workorder_ids:
                    if workorder.workcenter_id in incompatible_workcenters:
                        raise ValidationError(_(
                            'Centro de trabajo "%(wc)s" incompatible con producto "%(prod)s".\n'
                            'Seleccione un centro de trabajo alternativo.',
                            wc=workorder.workcenter_id.name,
                            prod=production.product_id.name
                        ))
