# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpAveriaCategoriaLinea(models.Model):
    """Detalle de la hoja "Registro Averías" (Fase 4).

    Una línea de Seguimiento de tiempo (una hora) puede tener más de un
    tipo de avería -- confirmado con Laura: "en esa hora pueden haber 1
    o varios tipos de averías". Por eso mrp.averia.linea ya no guarda
    una sola categoria_id/cantidad_averias: guarda una lista de estas
    líneas de detalle, una fila por categoría encontrada en esa hora.
    """
    _name = 'mrp.averia.categoria.linea'
    _description = "Detalle de categoría de avería"

    averia_linea_id = fields.Many2one(
        'mrp.averia.linea', required=True, ondelete='cascade')
    workcenter_tipo = fields.Selection(
        related='averia_linea_id.workcenter_tipo',
        store=True, readonly=True, string="Tipo de CT (interno)")
    categoria_id = fields.Many2one(
        'mrp.averia.categoria', required=True, string="Categoría de avería",
        domain="['|', ('tipo_centro_trabajo', '=', False), "
               "('tipo_centro_trabajo', '=', workcenter_tipo)]")
    cantidad = fields.Integer(string="Cantidad", default=1)
    descripcion = fields.Text(
        string="Descripción",
        help="Texto libre, igual que en la hoja anterior -- la "
             "categoría es lo que se reporta/agrupa, esto es solo "
             "nota adicional del operador.")
