# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpAveriaLinea(models.Model):
    """Hoja de trabajo unificada "Registro Averías" (Fase 4).

    Reemplaza las dos hojas de trabajo separadas por tipo de operación
    (Inyección Hora Hora / Soplado Hora Hola) por un solo modelo,
    categorizado por Centro de Trabajo, Producto, Orden de Fabricación
    y Operación -- tal como lo pediste. Confirmado con Laura: no hace
    falta migrar histórico (ambiente de test) y solo se necesita un
    punto de control de averías, apuntando a este modelo.

    El campo quality_check_id es el que la vuelve una hoja de trabajo
    válida para el módulo de Calidad (quality_control_worksheet).

    PASO MANUAL PENDIENTE (no se hace por XML de datos, a propósito):
    después de instalar el módulo, registra este modelo como plantilla
    de hoja de trabajo desde Calidad -> Configuración -> Hojas de
    trabajo (el mismo camino con el que se crearon las dos plantillas
    anteriores), eligiendo el modelo "Registro Averías", y asígnala al
    único punto de control de averías. No se hizo por datos XML porque
    no tengo confirmado en vivo el nombre técnico exacto del modelo de
    plantillas de hoja de trabajo en esta instancia, y un dato XML mal
    apuntado puede tumbar la instalación para todo el ambiente de
    prueba compartido.
    """
    _name = 'mrp.averia.linea'
    _description = "Registro Averías"

    quality_check_id = fields.Many2one(
        'quality.check', required=True, ondelete='cascade')
    categoria_id = fields.Many2one(
        'mrp.averia.categoria', string="Categoría de avería",
        domain="['|', ('tipo_centro_trabajo', '=', False), "
               "('tipo_centro_trabajo', '=', workcenter_tipo)]")
    cantidad_averias = fields.Integer(string="Cantidad")

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
