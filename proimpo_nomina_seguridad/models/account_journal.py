# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    proimpo_confidencial = fields.Boolean(
        string="Diario confidencial (nomina)",
        help="Si esta marcado, solo los usuarios del grupo 'Nomina Confidencial' veran los "
             "asientos de este diario. El resto de la contabilidad no los vera.")
