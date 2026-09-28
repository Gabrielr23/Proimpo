# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    consumed = fields.Boolean(
        string="Consumo en produccion",
        help="Marcar en los tipos de operación que llevan componentes a "
             "pre-producción (p. ej. Pick Components). Solo las transferencias "
             "de estos tipos (y sus devoluciones) cuentan para la Cantidad "
             "hecha de las órdenes de fabricación.")
