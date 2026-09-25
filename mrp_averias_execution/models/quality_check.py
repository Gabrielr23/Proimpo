# -*- coding: utf-8 -*-
from odoo import api, fields, models


class QualityCheck(models.Model):
    """Expone el detalle de averías directamente en el control de
    calidad (Fase 4, ajuste post-prueba).

    Laura desvinculó su hoja de trabajo (Studio) del punto de control
    QCP00017 y cambió su Tipo a "Registrar cantidad" -- con eso, el
    control de calidad ya no muestra ningún dato de averías, y sin esa
    data no se puede aprobar/fallar con criterio. En vez de depender
    del mecanismo nativo de plantillas de hoja de trabajo (frágil,
    ligado al Tipo del punto de control), este módulo embebe su propio
    detalle -- vía mrp.averia.categoria.linea.quality_check_id, que es
    un related/store hacia acá -- para que quede visible sin importar
    cómo esté configurado el punto de control.
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
