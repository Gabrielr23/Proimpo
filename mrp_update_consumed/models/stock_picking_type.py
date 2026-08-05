# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import odoo.addons.decimal_precision as dp


class PickingType(models.Model):
    _inherit = "stock.picking.type"

    consumed = fields.Boolean(string="Consumo en produccion")

