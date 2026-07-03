# -*- coding: utf-8 -*-
from odoo import models, fields
from dateutil.relativedelta import relativedelta
import datetime


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # Códigos de horas extra/recargos (se excluyen de la base de vacaciones)
    LIQ_EXTRA_CODES = ('HED', 'HEN', 'HRN', 'HEDDF', 'HRDDF', 'HENDF', 'HRNDF')

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    @staticmethod
    def _liq_dias360(d1, d2):
        """Días comerciales (meses de 30) entre d1 y d2, inclusivos."""
        if not d1 or not d2 or d2 < d1:
            return 0
        a1 = min(d1.day, 30)
        a2 = min(d2.day, 30)
        return (d2.year - d1.year) * 360 + (d2.month - d1.month) * 30 + (a2 - a1) + 1

    def _liq_cat_total(self, slip, catcode):
        return sum(l.total for l in slip.line_ids
                   if l.category_id and l.category_id.code == catcode)

    def _liq_line_total(self, slip, codes):
        return sum(l.total for l in slip.line_ids
                   if l.salary_rule_id.code in codes)

    # ------------------------------------------------------------------
    # Promedio del último año (excluye meses de suspensión sin devengo)
    # ------------------------------------------------------------------
    def _liq_promedios(self, date_end):
        """Promedio mensual devengado de los 12 meses previos a date_end.

        Devuelve un dict con promedios de: básico, devengado salarial (incluye extras),
        extras (para excluirlas en vacaciones) y auxilio de transporte. El divisor es el
        número de meses con devengo efectivo (los meses en suspensión no cuentan).
        """
        self.ensure_one()
        desde = date_end - relativedelta(months=12)
        slips = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '>=', desde),
            ('date_to', '<=', date_end),
            ('state', 'in', ('done', 'paid')),
            ('id', '!=', self.id),
        ])
        meses = {}
        for s in slips:
            k = (s.date_from.year, s.date_from.month)
            d = meses.setdefault(k, {'bas': 0.0, 'dev': 0.0, 'ext': 0.0, 'tra': 0.0, 'gross': 0.0})
            d['bas'] += self._liq_cat_total(s, 'BASIC')
            d['dev'] += self._liq_cat_total(s, 'DEVSAL')
            d['ext'] += self._liq_line_total(s, self.LIQ_EXTRA_CODES)
            d['tra'] += self._liq_cat_total(s, 'AUXT')
            d['gross'] += self._liq_cat_total(s, 'GROSS')
        efectivos = [d for d in meses.values() if d['gross'] > 0]
        n = len(efectivos) or 1
        s_ = lambda key: sum(d[key] for d in efectivos) / n
        return {
            'meses': n,
            'basico': s_('bas'),
            'devsal': s_('dev'),
            'extras': s_('ext'),
            'transporte': s_('tra'),
        }

    def _liq_base(self, tipo):
        """Base salarial según el concepto a liquidar."""
        p = self._liq_promedios(self.date_to)
        salario = self.contract_id.wage
        # Si no hay historial suficiente, usar el salario del contrato como piso
        fijo = p['basico'] if p['basico'] > 0 else salario
        if tipo == 'prest':      # cesantías y prima: incluye transporte
            return fijo + p['devsal'] + p['transporte']
        elif tipo == 'indem':    # indemnización: fijo + variables, sin transporte
            return fijo + p['devsal']
        elif tipo == 'vac':      # vacaciones: sin extras y sin transporte
            return fijo + (p['devsal'] - p['extras'])
        return 0.0

    # ------------------------------------------------------------------
    # Fechas de inicio de cada acumulado
    # ------------------------------------------------------------------
    def _liq_desde(self, tipo):
        """Fecha desde la que se acumula cada concepto (recortada al inicio del contrato)."""
        ini = self.contract_id.date_start
        ret = self.date_to
        if tipo == 'cesantias':
            base = datetime.date(ret.year, 1, 1)
        elif tipo == 'prima':
            base = datetime.date(ret.year, 1 if ret.month <= 6 else 7, 1)
        else:  # vacaciones: desde el inicio del contrato
            base = ini
        return max(base, ini) if ini else base

    # ------------------------------------------------------------------
    # Conceptos de liquidación
    # ------------------------------------------------------------------
    def _liq_cesantias(self):
        base = self._liq_base('prest')
        dias = self._liq_dias360(self._liq_desde('cesantias'), self.date_to)
        return base * dias / 360.0

    def _liq_intereses_cesantias(self):
        base = self._liq_base('prest')
        dias = self._liq_dias360(self._liq_desde('cesantias'), self.date_to)
        cesantias = base * dias / 360.0
        return cesantias * dias * 0.12 / 360.0

    def _liq_prima(self):
        base = self._liq_base('prest')
        dias = self._liq_dias360(self._liq_desde('prima'), self.date_to)
        return base * dias / 360.0

    def _liq_vacaciones(self, dias_disfrutados=0.0):
        base = self._liq_base('vac')
        dias_trab = self._liq_dias360(self._liq_desde('vacaciones'), self.date_to)
        dias_causados = dias_trab * 15.0 / 360.0
        return base / 30.0 * max(dias_causados - (dias_disfrutados or 0.0), 0.0)

    # ------------------------------------------------------------------
    # Indemnización por despido sin justa causa (Art. 64 CST)
    # ------------------------------------------------------------------
    def _liq_tipo_contrato(self):
        """Tipo colombiano de contrato (campo type_contract_id de Jorels).
        Codigos: 1=Termino fijo, 2=Indefinido, 3=Obra o labor, 4=Aprendizaje, 5=Practicas."""
        tc = getattr(self.contract_id, 'type_contract_id', False)
        code = (tc.code or '').strip() if tc else ''
        name = (tc.name or '').lower() if tc else ''
        if code == '1' or 'fij' in name:
            return 'fijo'
        if code == '3' or 'obra' in name or 'labor' in name:
            return 'obra'
        if code in ('4', '5') or 'aprend' in name or 'pasant' in name or 'practic' in name or 'práctic' in name:
            return 'aprendiz'
        return 'indefinido'

    def _liq_indemnizacion(self):
        """Indemnización por despido sin justa causa. Devuelve 0 si es con justa causa
        (para ello no se digita / la regla se condiciona por una entrada)."""
        contract = self.contract_id
        smmlv = contract.company_id.smmlv_value or 0.0
        base = self._liq_base('indem')
        dia = base / 30.0
        tipo = self._liq_tipo_contrato()
        ret = self.date_to

        if tipo == 'aprendiz':
            return 0.0

        if tipo == 'fijo':
            # Salarios que faltan hasta la fecha pactada de terminación
            fin = contract.date_end
            if fin and fin > ret:
                dias_faltan = self._liq_dias360(ret, fin) - 1
                return dia * max(dias_faltan, 0)
            return 0.0

        if tipo == 'obra':
            # Salarios del tiempo que falte para la obra, mínimo 15 días
            return dia * 15.0

        # Indefinido: tabla Art. 64
        antig = self._liq_dias360(contract.date_start, ret)
        menor = contract.wage < 10.0 * smmlv
        if antig <= 360:
            dias_indem = 30.0 if menor else 20.0
        else:
            extra = (antig - 360) / 360.0
            dias_indem = (30.0 + 20.0 * extra) if menor else (20.0 + 15.0 * extra)
        return dia * dias_indem
