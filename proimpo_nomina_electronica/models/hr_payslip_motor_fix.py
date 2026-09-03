# -*- coding: utf-8 -*-
"""Tolerancia del motor (l10n_co_hr_payroll_enterprise) a lineas de devengado sin fechas.

Al calcular el recibo, el motor arma su payload JSON (edi_payload) y para horas extras /
recargos llama _format_date_hours(date_start, time_start). Si la linea se capturo a mano sin
"Fecha de inicio"/"Fecha final", date_start es False y explota con
AttributeError: 'bool' object has no attribute 'year'.
Ese payload solo lo usa Jorels (que PROIMPO no utiliza), asi que basta con no fallar:
se usa como respaldo la fecha de inicio/fin del periodo del recibo.
"""
from datetime import datetime, timedelta
from odoo import fields, models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _format_date_hours(self, date, hours):
        if not date:
            date = (self.date_from if len(self) == 1 else False) or fields.Date.context_today(self)
        date_hours = datetime(date.year, date.month, date.day) + timedelta(hours=hours or 0.0)
        return fields.Datetime.to_string(date_hours)
