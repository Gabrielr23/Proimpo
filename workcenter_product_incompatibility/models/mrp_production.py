from odoo import models, api, _
from odoo.exceptions import ValidationError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    
    @api.constrains('product_id', 'workorder_ids')
    def _check_workcenter_compatibility(self):
        """Validar que no se asignen centros incompatibles"""
        for production in self:
            incompatible_workcenters = production.product_id._get_incompatible_workcenters()
            for workorder in production.workorder_ids:
                if workorder.workcenter_id in incompatible_workcenters:
                    raise ValidationError(_(
                        'El centro de trabajo "%s" no es compatible con el producto "%s".\n'
                        'Por favor, seleccione un centro de trabajo alternativo.'
                    ) % (workorder.workcenter_id.name, production.product_id.name))