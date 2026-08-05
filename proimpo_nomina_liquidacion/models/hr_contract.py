# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo import models

# MOTOR UNICO de prestaciones sociales (calculo legal).
# Base = promedio de los ultimos 12 meses (meses con devengo efectivo).
#   Cesantias/prima/intereses: basico + variable + auxilio de transporte.
#   Vacaciones: basico + variable - horas extra (sin transporte).
LIQ_EXTRA_CODES = ('HED', 'HEN', 'HRN', 'HEDDF', 'HRDDF', 'HENDF', 'HRNDF')
COD_VAC_PAG = ('VAC', 'VACDISF', 'VACACIONES')


def dias360(d1, d2):
    if not d1 or not d2 or d2 < d1:
        return 0
    a1 = min(d1.day, 30)
    a2 = min(d2.day, 30)
    return (d2.year - d1.year) * 360 + (d2.month - d1.month) * 30 + (a2 - a1) + 1


class HrContract(models.Model):
    _inherit = 'hr.contract'

    def _proimpo_promedios(self, date_end):
        """Promedio mensual de los 12 meses previos a date_end (solo meses con devengo)."""
        self.ensure_one()
        desde = date_end - relativedelta(months=12)
        slips = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '>=', desde), ('date_to', '<=', date_end),
            ('state', 'in', ('done', 'paid'))])
        meses = {}
        for s in slips:
            k = (s.date_from.year, s.date_from.month)
            d = meses.setdefault(k, {'bas': 0., 'dev': 0., 'ext': 0., 'tra': 0., 'gross': 0.})
            for l in s.line_ids:
                cat = l.category_id.code if l.category_id else ''
                if cat == 'BASIC':
                    d['bas'] += l.total
                elif cat == 'DEVSAL':
                    d['dev'] += l.total
                elif cat == 'AUXT':
                    d['tra'] += l.total
                elif cat == 'GROSS':
                    d['gross'] += l.total
                if l.salary_rule_id.code in LIQ_EXTRA_CODES:
                    d['ext'] += l.total
        efect = [d for d in meses.values() if d['gross'] > 0]
        n = len(efect) or 1
        f = lambda key: sum(d[key] for d in efect) / n
        return {'basico': f('bas'), 'devsal': f('dev'), 'extras': f('ext'), 'transporte': f('tra')}

    def _proimpo_base(self, tipo, date_end):
        """Base salarial legal segun el concepto a liquidar."""
        self.ensure_one()
        p = self._proimpo_promedios(date_end)
        fijo = p['basico'] if p['basico'] > 0 else (self.wage or 0.0)
        if tipo == 'prest':      # cesantias, prima, intereses: incluye transporte
            return fijo + p['devsal'] + p['transporte']
        if tipo == 'vac':        # vacaciones: sin horas extra ni transporte
            return fijo + (p['devsal'] - p['extras'])
        if tipo == 'indem':      # indemnizacion: fijo + variable, sin transporte
            return fijo + p['devsal']
        return 0.0

    def _proimpo_vac_pagadas(self, hasta):
        self.ensure_one()
        if not self.date_start:
            return 0.0
        slips = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id), ('state', 'in', ('done', 'paid')),
            ('date_from', '>=', self.date_start), ('date_to', '<=', hasta)])
        return sum(slips.mapped('line_ids').filtered(
            lambda l: l.salary_rule_id.code in COD_VAC_PAG).mapped('total'))

    def _proimpo_prestaciones_causadas(self, corte, smmlv=0.0, aux=0.0):
        """MOTOR UNICO. Causado real de prestaciones a la fecha 'corte' (calculo legal).
        smmlv/aux se aceptan por compatibilidad pero el transporte sale del promedio real."""
        self.ensure_one()
        ct = self
        cero = {'ces': 0., 'int': 0., 'prima': 0., 'vac': 0., 'base_ces': 0., 'base_vac': 0.,
                'dias_ano': 0, 'dias_sem': 0, 'dias_tot': 0}
        if ct.integral_salary or not ct.date_start or ct.date_start > corte:
            return cero
        y = corte.year
        ini = ct.date_start
        d_ces = max(date(y, 1, 1), ini)
        d_pri = max(date(y, 1 if corte.month <= 6 else 7, 1), ini)
        base_prest = self._proimpo_base('prest', corte)
        base_vac = self._proimpo_base('vac', corte)
        dias_ces = dias360(d_ces, corte)
        dias_pri = dias360(d_pri, corte)
        dias_vac = dias360(ini, corte)
        ces = base_prest * dias_ces / 360.0
        interes = ces * dias_ces / 360.0 * 0.12
        prima = base_prest * dias_pri / 360.0
        vac = base_vac * dias_vac / 720.0 - self._proimpo_vac_pagadas(corte)
        return {'ces': ces, 'int': interes, 'prima': prima, 'vac': vac,
                'base_ces': base_prest, 'base_vac': base_vac,
                'dias_ano': dias_ces, 'dias_sem': dias_pri, 'dias_tot': dias_vac}
