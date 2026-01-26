from odoo import models, fields, api, _


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
        compute='_compute_incompatible_product_count',
        store=False
    )

    @api.depends('incompatible_product_ids')
    def _compute_incompatible_product_count(self):
        """Contar productos incompatibles"""
        for record in self:
            record.incompatible_product_count = len(record.incompatible_product_ids)

    def is_compatible_with_product(self, product):
        """Verifica si este centro de trabajo es compatible con el producto"""
        self.ensure_one()
        if isinstance(product, int):
            product = self.env['product.product'].browse(product)

        product_template = product.product_tmpl_id if hasattr(product, 'product_tmpl_id') else product
        return product_template not in self.incompatible_product_ids
