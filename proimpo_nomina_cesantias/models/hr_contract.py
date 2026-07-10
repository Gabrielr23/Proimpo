# -*- coding: utf-8 -*-
from odoo import models, fields


class HrContract(models.Model):
    _inherit = 'hr.contract'

    fondo_cesantias = fields.Selection(
        [('PORVENIR', 'Porvenir'), ('PROTECCION', 'Proteccion'),
         ('COLFONDOS', 'Colfondos'), ('FONDO', 'FNA (Fondo Nacional del Ahorro)'),
         ('SKANDIA', 'Skandia')],
        string="Fondo de cesantias",
        help="Fondo al que se consignan las cesantias del trabajador (para el plano anual).")
