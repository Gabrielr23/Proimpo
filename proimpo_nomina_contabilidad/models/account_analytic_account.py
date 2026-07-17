# -*- coding: utf-8 -*-
from odoo import models, fields

AREAS = [
    ('admin', 'Administrativos (5105)'),
    ('ventas', 'Ventas (5205)'),
    ('operarios', 'Operarios Produccion (7201)'),
    ('admprod', 'Admon Produccion (7301)'),
]


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    proimpo_area = fields.Selection(
        AREAS, string="Area contable (nomina)",
        help="Grupo de cuentas que se usara al contabilizar la nomina de los contratos con "
             "este centro de costo.")
