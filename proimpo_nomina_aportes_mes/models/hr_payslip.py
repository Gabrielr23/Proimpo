# -*- coding: utf-8 -*-
from odoo import models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # ------------------------------------------------------------------
    # Auxiliares para reconciliar contra la 1Q
    # ------------------------------------------------------------------
    def _am_es_2q(self):
        self.ensure_one()
        return bool(self.date_from and self.date_from.day > 15)

    def _am_slip_1q(self):
        """Recibo de la 1Q del mismo empleado y mes."""
        self.ensure_one()
        if not self.date_from:
            return self.browse()
        cands = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id),
            ('date_from', '>=', self.date_from.replace(day=1)),
            ('date_from', '<=', self.date_from.replace(day=15)),
            ('state', '!=', 'cancel'),
        ])
        if not cands:
            return self.browse()
        # Prefiere: (1) estado mas avanzado, (2) que ya este calculado (tiene lineas),
        # (3) el mas reciente. Asi evita los borradores viejos/vacios pero usa el 1Q
        # aunque quede en borrador, siempre que este calculado.
        rank = {'paid': 3, 'done': 3, 'verify': 2, 'draft': 1}
        return max(cands, key=lambda s: (rank.get(s.state, 0), 1 if s.line_ids else 0, s.id))

    def _am_line_total(self, code):
        """Total de una regla (por código) en este recibo ya calculado."""
        self.ensure_one()
        return sum(l.total for l in self.line_ids if l.salary_rule_id.code == code)

    def _proimpo_ibc_mes(self, ibc_quincena):
        """IBC del MES = IBC de esta quincena + IBC de la 1Q (si es 2Q)."""
        self.ensure_one()
        total = ibc_quincena or 0.0
        if self._am_es_2q():
            slip1 = self._am_slip_1q()
            if slip1:
                total += slip1._am_line_total('IBC')
        return total

    # ------------------------------------------------------------------
    # FSP con tramo sobre el IBC del MES (incluye el adicional > 16 SMMLV)
    # ------------------------------------------------------------------
    def _proimpo_fsp(self, ibc_quincena):
        """Devuelve el FSP del período (valor NEGATIVO, deducción), con el tramo
        calculado sobre el IBC del MES y reconciliando lo aplicado en la 1Q."""
        self.ensure_one()
        smmlv = self.contract_id.company_id.smmlv_value or 0.0
        ibc_mes = self._proimpo_ibc_mes(ibc_quincena)
        r = (ibc_mes / smmlv) if smmlv else 0.0
        if 4 <= r < 16:
            p = 0.010
        elif 16 <= r < 17:
            p = 0.012
        elif 17 <= r < 18:
            p = 0.014
        elif 18 <= r < 19:
            p = 0.016
        elif 19 <= r < 20:
            p = 0.018
        elif r >= 20:
            p = 0.020
        else:
            p = 0.0
        fsp_mes = ibc_mes * p
        fsp_1q = 0.0
        if self._am_es_2q():
            slip1 = self._am_slip_1q()
            if slip1:
                fsp_1q = abs(slip1._am_line_total('FSP'))
        return - max(fsp_mes - fsp_1q, 0.0)

    # ------------------------------------------------------------------
    # Parafiscales / salud empleador: exoneración sobre el IBC del MES
    # ------------------------------------------------------------------
    def _proimpo_parafiscal(self, ibc_quincena, tasa, code_1q):
        """Aporte patronal (SENA/ICBF/salud empleador) con exoneración Art. 114-1
        evaluada sobre el IBC del MES (>= 10 SMMLV). Reconcilia lo aplicado en la 1Q.
        Devuelve el valor POSITIVO."""
        self.ensure_one()
        smmlv = self.contract_id.company_id.smmlv_value or 0.0
        ibc_mes = self._proimpo_ibc_mes(ibc_quincena)
        if smmlv and ibc_mes < 10.0 * smmlv:
            return 0.0  # exonerado (gana menos de 10 SMMLV en el mes)
        aporte_mes = ibc_mes * tasa
        ya_1q = 0.0
        if self._am_es_2q():
            slip1 = self._am_slip_1q()
            if slip1:
                ya_1q = slip1._am_line_total(code_1q)
        return max(aporte_mes - ya_1q, 0.0)

    # ------------------------------------------------------------------
    # Auxilio de transporte: se retira si básico + comisiones del MES > 2 SMMLV
    # ------------------------------------------------------------------
    def _proimpo_transporte_ajuste(self, trans_quincena, sal_quincena):
        """Ajuste del auxilio de transporte. En la 2Q, si el ingreso salarial del
        MES (básico + comisiones = BASIC + DEVSAL, 1Q + 2Q) supera 2 SMMLV, retira
        el auxilio de todo el mes (clawback: -2Q y -1Q). En la 1Q no ajusta.
        Devuelve el ajuste (0 o negativo)."""
        self.ensure_one()
        smmlv = self.contract_id.company_id.smmlv_value or 0.0
        if not self._am_es_2q() or not smmlv:
            return 0.0
        slip1 = self._am_slip_1q()
        sal_1q = 0.0
        trans_1q = 0.0
        if slip1:
            sal_1q = sum(l.total for l in slip1.line_ids
                         if l.category_id and l.category_id.code in ('BASIC', 'DEVSAL'))
            trans_1q = slip1._am_line_total('TRANS')
        sal_mes = (sal_quincena or 0.0) + sal_1q
        if sal_mes > 2.0 * smmlv:
            return - ((trans_quincena or 0.0) + trans_1q)
        return 0.0
