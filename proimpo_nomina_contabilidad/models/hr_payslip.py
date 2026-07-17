# -*- coding: utf-8 -*-
from odoo import models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _proimpo_area(self):
        self.ensure_one()
        aa = self.contract_id.analytic_account_id
        return aa.proimpo_area if aa else False

    def _prepare_line_values(self, line, account_id, date, debit, credit):
        """Sustituye la cuenta segun el area (centro de costo) del contrato."""
        area = self._proimpo_area()
        if area and line.salary_rule_id.code:
            mapeo = self.env['proimpo.cuenta.mapeo'].search([
                ('rule_code', '=', line.salary_rule_id.code),
                ('area', '=', area)], limit=1)
            if mapeo:
                if debit and mapeo.account_debit_id:
                    account_id = mapeo.account_debit_id.id
                elif credit and mapeo.account_credit_id:
                    account_id = mapeo.account_credit_id.id
        return super()._prepare_line_values(line, account_id, date, debit, credit)
