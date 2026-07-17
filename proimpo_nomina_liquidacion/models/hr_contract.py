# -*- coding: utf-8 -*-
from datetime import date
from odoo import models

# Motor unico de prestaciones sociales. Base canonica: ultimo basico +
# promedio de variables + auxilio de transporte (segun prestacion), dias 360.
CAT_SALARIAL = 'DEVSAL'
COD_BASICO = ['BASIC', 'BASICO']
COD_VAC_PAG = ['VAC', 'VACDISF', 'VACACIONES']


def dias360(d1, d2):
    if not d1 or not d2 or d2 < d1:
        return 0
    a1 = min(d1.day, 30)
    a2 = min(d2.day, 30)
    return (d2.year - d1.year) * 360 + (d2.month - d1.month) * 30 + (a2 - a1) + 1


class HrContract(models.Model):
    _inherit = 'hr.contract'

    def _proimpo_slips_periodo(self, d1, d2):
        return self.env['hr.payslip'].search([
            ('contract_id', '=', self.id), ('state', 'in', ('done', 'paid')),
            ('date_from', '>=', d1), ('date_to', '<=', d2)])

    def _proimpo_promedio_variable(self, d1, d2):
        """Promedio mensual de factores salariales variables (DEVSAL menos basico)."""
        slips = self._proimpo_slips_periodo(d1, d2)
        if not slips:
            return 0.0
        lines = slips.mapped('line_ids').filtered(
            lambda l: l.category_id.code == CAT_SALARIAL and l.salary_rule_id.code not in COD_BASICO)
        var = sum(lines.mapped('total'))
        meses = dias360(d1, d2) / 30.0
        return var / meses if meses else 0.0

    def _proimpo_vac_pagadas(self, hasta):
        slips = self._proimpo_slips_periodo(self.date_start, hasta)
        if not slips:
            return 0.0
        return sum(slips.mapped('line_ids').filtered(
            lambda l: l.salary_rule_id.code in COD_VAC_PAG).mapped('total'))

    def _proimpo_prestaciones_causadas(self, corte, smmlv=0.0, aux=0.0):
        """MOTOR UNICO. Devuelve el causado real de prestaciones a la fecha 'corte'.
        {'ces','int','prima','vac','base_ces','base_vac','dias_ano','dias_sem','dias_tot'}"""
        self.ensure_one()
        ct = self
        smmlv = smmlv or (ct.company_id.smmlv_value or 0.0)
        cero = {'ces': 0.0, 'int': 0.0, 'prima': 0.0, 'vac': 0.0, 'base_ces': 0.0,
                'base_vac': 0.0, 'dias_ano': 0, 'dias_sem': 0, 'dias_tot': 0}
        if ct.integral_salary or not ct.date_start or ct.date_start > corte:
            return cero
        y = corte.year
        ene1 = date(y, 1, 1)
        sem1 = date(y, 7, 1) if corte.month >= 7 else date(y, 1, 1)
        d_ano = max(ct.date_start, ene1)
        d_sem = max(ct.date_start, sem1)
        transp = aux if (aux and ct.wage <= 2 * smmlv) else 0.0
        prom_ano = self._proimpo_promedio_variable(d_ano, corte)
        prom_sem = self._proimpo_promedio_variable(d_sem, corte)
        base_ces = ct.wage + transp + prom_ano
        base_prima = ct.wage + transp + prom_sem
        base_vac = ct.wage + prom_ano          # vacaciones NO incluye transporte
        dias_ano = dias360(d_ano, corte)
        dias_sem = dias360(d_sem, corte)
        dias_tot = dias360(ct.date_start, corte)
        ces = base_ces * dias_ano / 360.0
        interes = ces * dias_ano / 360.0 * 0.12
        prima = base_prima * dias_sem / 360.0
        vac_acum = base_vac * dias_tot / 720.0
        vac = vac_acum - self._proimpo_vac_pagadas(corte)
        return {
            'ces': ces, 'int': interes, 'prima': prima, 'vac': vac,
            'base_ces': base_ces, 'base_vac': base_vac,
            'dias_ano': dias_ano, 'dias_sem': dias_sem, 'dias_tot': dias_tot,
        }
