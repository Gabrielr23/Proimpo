# -*- coding: utf-8 -*-
from datetime import date
from odoo import models, fields, api


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

    # Categorias que Jorels cuantifica en DIAS (ausencias) y en HORAS (extras/recargos)
    _CAT_DIAS = {
        'vacation_common',
        'licensings_maternity_or_paternity_leaves',
        'licensings_permit_or_paid_licenses',
        'licensings_suspension_or_unpaid_leaves',
        'incapacities_common', 'incapacities_professional', 'incapacities_working',
        'legal_strikes',
    }
    _CAT_HORAS = {
        'daily_overtime', 'overtime_night_hours', 'hours_night_surcharge',
        'sunday_holiday_daily_overtime', 'daily_surcharge_hours_sundays_holidays',
        'sunday_night_overtime_holidays', 'sunday_holidays_night_surcharge_hours',
    }

    # Hacer editable la cantidad (el base la deja readonly por ser calculada). Se mantiene
    # el calculo del base cuando se usa rango de fechas/horas; si no, respeta lo digitado.
    quantity = fields.Float(readonly=False)

    @api.depends('date_start', 'date_end', 'time_start', 'time_end', 'category')
    def _compute_quantity(self):
        for rec in self:
            if rec.category in self._CAT_DIAS and rec.date_start and rec.date_end:
                rec.quantity = (rec.date_end - rec.date_start).days + 1
            elif rec.category in self._CAT_HORAS:
                if rec.date_start and rec.date_end and (rec.time_start or rec.time_end):
                    days = (rec.date_end - rec.date_start).days
                    rec.quantity = 24 * days + rec.time_end - rec.time_start
                elif not rec.quantity:
                    # Sin rango horario: permitir digitar la cantidad manualmente.
                    rec.quantity = 1
            elif not rec.quantity:
                rec.quantity = 1

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
