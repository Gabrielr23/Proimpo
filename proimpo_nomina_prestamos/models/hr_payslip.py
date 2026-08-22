# -*- coding: utf-8 -*-
from odoo import models, fields


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _proimpo_apply_loans(self):
        """Abona la cuota de cada préstamo/libranza activo y reduce el saldo."""
        LoanLine = self.env['hr.employee.loan.line']
        for slip in self:
            employee = slip.contract_id.employee_id or slip.employee_id
            if not employee:
                continue
            loans = self.env['hr.employee.loan'].search([
                ('employee_id', '=', employee.id), ('state', '=', 'open')])
            for loan in loans:
                if loan.line_ids.filtered(lambda l: l.payslip_id.id == slip.id):
                    continue
                cuota = loan.get_installment_for_date(slip.date_to, slip)
                if cuota <= 0:
                    continue
                LoanLine.create({
                    'loan_id': loan.id,
                    'payslip_id': slip.id,
                    'date': slip.date_to or fields.Date.context_today(self),
                    'amount': cuota,
                })
                if loan.amount_residual <= 0:
                    loan.state = 'done'

    def _proimpo_revert_loans(self):
        """Reversa los abonos asociados a estos recibos (restaura saldos)."""
        lines = self.env['hr.employee.loan.line'].search([('payslip_id', 'in', self.ids)])
        loans = lines.mapped('loan_id')
        lines.unlink()
        loans.filtered(lambda l: l.state == 'done' and l.amount_residual > 0).write({'state': 'open'})

    def action_payslip_done(self):
        res = super().action_payslip_done()
        self._proimpo_apply_loans()
        return res

    def action_payslip_draft(self):
        self._proimpo_revert_loans()
        return super().action_payslip_draft()

    def action_payslip_cancel(self):
        self._proimpo_revert_loans()
        return super().action_payslip_cancel()
