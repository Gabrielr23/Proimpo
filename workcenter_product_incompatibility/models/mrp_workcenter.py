from odoo import models, fields, api

class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'
    
    incompatible_product_ids = fields.Many2many(
        'product.template',
        'product_workcenter_incompatibility_rel',
        'workcenter_id',
        'product_tmpl_id',
        string='Productos Incompatibles',
        help='Productos que NO pueden ser procesados en este centro de trabajo'
    )
    
    incompatible_product_count = fields.Integer(
        string='Productos Incompatibles',
        compute='_compute_incompatible_product_count'
    )
    
    @api.depends('incompatible_product_ids')
    def _compute_incompatible_product_count(self):
        for record in self:
            record.incompatible_product_count = len(record.incompatible_product_ids)
    
    def is_compatible_with_product(self, product):
        """Verifica si este centro de trabajo es compatible con el producto"""
        if isinstance(product, int):
            product = self.env['product.product'].browse(product)
        
        # Verificar incompatibilidad
        if product.product_tmpl_id in self.incompatible_product_ids:
            return False
        return True