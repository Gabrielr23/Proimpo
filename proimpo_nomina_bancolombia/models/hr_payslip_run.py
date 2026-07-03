# -*- coding: utf-8 -*-
from odoo import models


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_generar_bancolombia(self):
        self.ensure_one()
        return self.slip_ids.action_generar_bancolombia()
