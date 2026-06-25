# -*- coding: utf-8 -*-
from datetime import date
from odoo import models, api


class EarnLine(models.Model):
    _inherit = 'l10n_co_hr_payroll.earn.line'

    # Factor por categoria DIAN = (valor hora) x factor. Ajuste estos valores
    # si cambia su criterio (p. ej. dominicales al 80% por la reforma).
    _FACTORES_HORA = {
        'daily_overtime': 1.25,                          # HED  Hora extra diurna
        'overtime_night_hours': 1.75,                    # HEN  Hora extra nocturna
        'hours_night_surcharge': 0.35,                   # HRN  Recargo nocturno
        'sunday_holiday_daily_overtime': 2.00,           # HEDDF
        'daily_surcharge_hours_sundays_holidays': 0.75,  # HRDDF
        'sunday_night_overtime_holidays': 2.50,          # HENDF
        'sunday_holidays_night_surcharge_hours': 1.10,   # HRNDF
    }

    @api.onchange('rule_input_id')
    def _onchange_valor_hora_extra(self):
        """Al elegir el concepto, llena el Importe con el valor por hora del contrato."""
        for rec in self:
            categoria = rec.rule_input_id.input_id.earn_category if rec.rule_input_id else False
            factor = self._FACTORES_HORA.get(categoria)
            contrato = rec.payslip_id.contract_id
            if factor and contrato and contrato.wage:
                fecha = rec.payslip_id.date_to or date.today()
                divisor = 220.0 if fecha < date(2026, 7, 15) else 210.0
                rec.amount = round(contrato.wage / divisor * factor, 2)
