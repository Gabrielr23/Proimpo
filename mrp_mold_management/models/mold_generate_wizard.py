# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpMoldGenerateWizard(models.TransientModel):
    _name = 'mrp.mold.generate.wizard'
    _description = 'Generar equipos-molde desde los productos de la categoría Moldes'

    category_names = fields.Char(
        string='Categoría', compute='_compute_counts', readonly=True)
    total_products = fields.Integer(
        string='Productos en la categoría', compute='_compute_counts')
    already_count = fields.Integer(
        string='Ya tienen molde', compute='_compute_counts')
    link_count = fields.Integer(
        string='Se vincularán a un molde existente', compute='_compute_counts',
        help='Moldes ya creados a mano, sin producto, cuya Referencia de '
             'Molde coincide con la Referencia Interna de un producto.')
    create_count = fields.Integer(
        string='Se crearán moldes nuevos', compute='_compute_counts')

    state = fields.Selection(
        [('draft', 'Borrador'), ('done', 'Hecho')], default='draft')
    result_message = fields.Text(string='Resultado', readonly=True)

    @api.model
    def _get_products(self):
        Equipment = self.env['maintenance.equipment'].sudo()
        cats = Equipment._mold_category_ids()
        if not cats:
            return self.env['product.product']
        return self.env['product.product'].sudo().search(
            [('categ_id', 'in', list(cats))])

    @api.depends('state')
    def _compute_counts(self):
        Equipment = self.env['maintenance.equipment'].sudo().with_context(
            active_test=False)
        productos = self._get_products()
        cats = self.env['maintenance.equipment']._mold_categories()
        con_molde = Equipment.search(
            [('product_id', 'in', productos.ids)]).mapped('product_id')
        pendientes = productos - con_molde
        huerfanos = Equipment.search([
            ('is_mold', '=', True),
            ('product_id', '=', False),
            ('mold_code', '!=', False),
        ])
        codigos = set(huerfanos.mapped('mold_code'))
        vincular = pendientes.filtered(lambda p: p.default_code in codigos)
        for wiz in self:
            wiz.category_names = ', '.join(cats.mapped('complete_name')) or (
                'NO SE ENCONTRÓ la categoría Moldes')
            wiz.total_products = len(productos)
            wiz.already_count = len(con_molde)
            wiz.link_count = len(vincular)
            wiz.create_count = len(pendientes) - len(vincular)

    def action_generate(self):
        self.ensure_one()
        productos = self._get_products()
        res = self.env['maintenance.equipment'].sudo()._create_from_products(
            productos)
        mensaje = (
            'Moldes creados: %(creados)s\n'
            'Vinculados a un molde que ya existía: %(vinculados)s\n'
            'Ya tenían molde (sin cambios): %(existentes)s'
        ) % res
        self.write({'state': 'done', 'result_message': mensaje})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_molds(self):
        return self.env['ir.actions.act_window']._for_xml_id(
            'mrp_mold_management.action_mold_equipment')
