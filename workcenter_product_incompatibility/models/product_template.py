from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    incompatible_workcenter_ids = fields.Many2many(
        'mrp.workcenter',
        'product_workcenter_incompatibility_rel',
        'product_tmpl_id',
        'workcenter_id',
        string='Centros de Trabajo Incompatibles',
        help='Centros de trabajo que NO pueden procesar este producto'
    )
    
    incompatible_workcenter_count = fields.Integer(
        string='Incompatibilidades',
        compute='_compute_incompatible_workcenter_count'
    )
    
    @api.depends('incompatible_workcenter_ids')
    def _compute_incompatible_workcenter_count(self):
        for record in self:
            record.incompatible_workcenter_count = len(record.incompatible_workcenter_ids)

class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    def _get_incompatible_workcenters(self):
        """Retorna los centros de trabajo incompatibles para esta variante"""
        return self.product_tmpl_id.incompatible_workcenter_ids