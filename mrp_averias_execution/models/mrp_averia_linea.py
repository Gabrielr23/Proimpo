# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpAveriaLinea(models.Model):
    """Hoja de trabajo unificada "Registro Averías" (Fase 4).

    Reemplaza las dos hojas de trabajo separadas por tipo de operación
    (Inyección Hora Hora / Soplado Hora Hola) por un solo modelo,
    categorizado por Centro de Trabajo, Producto, Orden de Fabricación
    y Operación -- tal como lo pediste. Confirmado con Laura: no hace
    falta migrar histórico (ambiente de test) y solo se necesita un
    punto de control de averías, apuntando a este modelo.

    En esa misma hora puede haber más de un tipo de avería (confirmado
    con Laura), así que la categorización ya no es un solo
    categoria_id/cantidad_averias: son varias líneas de detalle
    (detalle_ids, modelo mrp.averia.categoria.linea), una fila por
    categoría encontrada.

    El campo quality_check_id la enlaza al control de calidad que la
    originó (m2o obligatorio). NO se registra como plantilla de hoja
    de trabajo nativa de Odoo (quality_control_worksheet) -- se probó
    ese camino y quedó frágil: dependía del Tipo del punto de control,
    y al cambiarlo se perdía la visibilidad de la data. En su lugar,
    el detalle de averías se embebe directamente en el formulario del
    control de calidad vía quality_check.py + la vista
    quality_check_views.xml, sin importar cómo esté configurado el
    punto de control. El botón "Tipificar" sigue abriendo esta hoja
    directamente, como ventana emergente.
    """
    _name = 'mrp.averia.linea'
    _description = "Registro Averías"

    quality_check_id = fields.Many2one(
        'quality.check', required=True, ondelete='cascade')
    detalle_ids = fields.One2many(
        'mrp.averia.categoria.linea', 'averia_linea_id',
        string="Categorías de avería")
    cantidad_averias_total = fields.Integer(
        string="Total averías", compute='_compute_cantidad_averias_total',
        store=True)

    # Campos de categorización -- llegan de la cadena
    # quality_check_id -> workorder_id -> production_id, no se
    # duplican a mano (pedido explícito: CT, producto, OF, operación).
    workcenter_id = fields.Many2one(
        'mrp.workcenter', related='quality_check_id.workorder_id.workcenter_id',
        store=True, string="Centro de trabajo")
    workcenter_tipo = fields.Selection(
        related='workcenter_id.tipo_centro_trabajo',
        store=True, readonly=True, string="Tipo de CT (interno)")
    product_id = fields.Many2one(
        'product.product', related='quality_check_id.product_id',
        store=True, string="Producto")
    production_id = fields.Many2one(
        'mrp.production', related='quality_check_id.production_id',
        store=True, string="Orden de fabricación")
    operacion_id = fields.Many2one(
        'mrp.routing.workcenter',
        related='quality_check_id.workorder_id.operation_id',
        store=True, string="Operación")

    @api.depends('detalle_ids.cantidad')
    def _compute_cantidad_averias_total(self):
        for rec in self:
            total = sum(rec.detalle_ids.mapped('cantidad'))
            rec.cantidad_averias_total = total
            rec._sync_averias_a_seguimiento(total)

    def _sync_averias_a_seguimiento(self, total):
        """Escribe el total de vuelta en la línea de Seguimiento de
        tiempo que originó el control de calidad (campo técnico Studio
        x_studio_linea_tiempo en quality.check -- mismo nombre que
        MrpWorkcenterProductivity.LINEA_FIELD).

        Antes la cantidad se cargaba en el wizard ANTES de abrir la
        hoja; ahora se carga DENTRO de la hoja (una fila por
        categoría), así que el camino se invirtió: la hoja es la que
        manda el total hacia Seguimiento de tiempo, no al revés.
        Confirmado con Laura: "agrego averias y no las totaliza en el
        seguimiento de tiempo" -- este es el arreglo.
        """
        self.ensure_one()
        linea_tiempo = self.quality_check_id.x_studio_linea_tiempo
        if linea_tiempo and linea_tiempo.x_studio_averias != total:
            linea_tiempo.sudo().write({'x_studio_averias': total})
