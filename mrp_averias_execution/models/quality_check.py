# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class QualityCheck(models.Model):
    """Expone el detalle de averías desde el control de calidad, vía
    botón inteligente (Fase 4, ajuste post-prueba nº2).

    Primer intento: embeber la tabla de averías directo en el
    formulario -- Laura reportó que aparecía en TODOS los controles de
    calidad (peso, dimensiones, etc.), no solo en los que tienen
    averías, porque el xpath apuntaba al formulario base compartido
    por todos los tipos de control. Corregido: ahora es un botón
    inteligente que solo se muestra cuando el control tiene averías
    (averia_cantidad_total > 0) y abre la hoja correspondiente -- igual
    de independiente del Tipo del punto de control que el intento
    anterior (no depende del mecanismo nativo de plantillas de hoja de
    trabajo), pero ya no ensucia los controles que no aplican.
    """
    _inherit = 'quality.check'

    averia_linea_ids = fields.One2many(
        'mrp.averia.linea', 'quality_check_id',
        string="Hoja de Averías")
    averia_detalle_ids = fields.One2many(
        'mrp.averia.categoria.linea', 'quality_check_id',
        string="Detalle de averías")
    averia_cantidad_total = fields.Integer(
        string="Total averías", compute='_compute_averia_cantidad_total')

    @api.depends('averia_detalle_ids.cantidad')
    def _compute_averia_cantidad_total(self):
        for rec in self:
            rec.averia_cantidad_total = sum(
                rec.averia_detalle_ids.mapped('cantidad'))

    def action_ver_averias(self):
        """Botón inteligente: abre la hoja de averías de ESTE control
        (y solo de este -- no la lista completa)."""
        self.ensure_one()
        linea = self.averia_linea_ids[:1]
        if not linea:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': _("Registro Averías"),
            'res_model': 'mrp.averia.linea',
            'res_id': linea.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }
