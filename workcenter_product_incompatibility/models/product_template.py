from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    incompatible_workcenter_ids = fields.Many2many(
        'mrp.workcenter',
        'product_workcenter_incompatibility_rel',
        'product_tmpl_id',
        'workcenter_id',
        string='Centros de Trabajo Incompatibles',
        help='Centros de trabajo donde este producto NO puede ser procesado'
    )

    incompatible_workcenter_count = fields.Integer(
        string='Cantidad de Incompatibles',
        compute='_compute_incompatible_workcenter_count',
        store=False
    )

    @api.depends('incompatible_workcenter_ids')
    def _compute_incompatible_workcenter_count(self):
        """Contar centros de trabajo incompatibles"""
        for record in self:
            record.incompatible_workcenter_count = len(record.incompatible_workcenter_ids)

    def _get_incompatible_workcenters(self):
        """Obtener centros de trabajo incompatibles"""
        return self.incompatible_workcenter_ids
