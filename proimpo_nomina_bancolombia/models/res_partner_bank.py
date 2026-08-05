# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    proimpo_tipo_cuenta = fields.Selection(
        [('ahorros', 'Ahorros'), ('corriente', 'Corriente')],
        string="Tipo de cuenta (Bancolombia)", default='ahorros')
