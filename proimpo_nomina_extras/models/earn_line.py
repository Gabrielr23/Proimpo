# -*- coding: utf-8 -*-
from datetime import date
from odoo import models, api


def recargo_dominical_pct(fecha):
    """Recargo dominical/festivo vigente segun la fecha (reforma laboral Ley 2466/2025).
    75% (hasta jun-2025) -> 80% (jul-2025) -> 90% (jul-2026) -> 100% (jul-2027)."""
    if fecha >= date(2027, 7, 1):
        return 1.00
    if fecha >= date(2026, 7, 1):
        return 0.90
    if fecha >= date(2025, 7, 1):
        return 0.80
    return 0.75


class EarnLine(models.Model):
    _inherit = 'l10n_co_hr_payroll.earn.line'

    # Parte FIJA del factor (sin el recargo dominical). Para las categorias dom/festivo
    # se le suma el recargo dominical vigente segun la fecha del recibo.
    _BASE_FIJA = {
        'daily_overtime': 1.25,                          # HED  = 1 + 0.25 extra diurna
        'overtime_night_hours': 1.75,                    # HEN  = 1 + 0.75 extra nocturna
        'hours_night_surcharge': 0.35,                   # HRN  = 0.35 recargo nocturno
        'sunday_holiday_daily_overtime': 1.25,           # HEDDF  = 1 + 0.25 + dominical
        'daily_surcharge_hours_sundays_holidays': 0.00,  # HRDDF  =           dominical
        'sunday_night_overtime_holidays': 1.75,          # HENDF  = 1 + 0.75 + dominical
        'sunday_holidays_night_surcharge_hours': 0.35,   # HRNDF  = 0.35 +     dominical
    }
    _LLEVA_DOMINICAL = {
        'sunday_holiday_daily_overtime',
        'daily_surcharge_hours_sundays_holidays',
        'sunday_night_overtime_holidays',
        'sunday_holidays_night_surcharge_hours',
    }

    def _factor_hora(self, categoria, fecha):
        """Factor (valor_hora x factor) segun categoria y fecha del recibo."""
        base = self._BASE_FIJA.get(categoria)
        if base is None:
            return None
        if categoria in self._LLEVA_DOMINICAL:
            return round(base + recargo_dominical_pct(fecha), 4)
        return base

    @api.onchange('rule_input_id')
    def _onchange_valor_hora_extra(self):
        """Al elegir el concepto, llena el Importe con el valor por hora del contrato."""
        for rec in self:
            categoria = rec.rule_input_id.input_id.earn_category if rec.rule_input_id else False
            contrato = rec.payslip_id.contract_id
            fecha = rec.payslip_id.date_to or date.today()
            factor = self._factor_hora(categoria, fecha)
            if factor and contrato and contrato.wage:
                divisor = 220.0 if fecha < date(2026, 7, 15) else 210.0
                rec.amount = round(contrato.wage / divisor * factor, 2)
