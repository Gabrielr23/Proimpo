# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class StockPicking(models.Model):
    _inherit = "stock.picking"

    totally_transferred = fields.Boolean(string="Transferido totalmente",
                                       help='Debe poner este check si se transfirio todo para la order de producción.')