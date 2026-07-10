# -*- coding: utf-8 -*-
from odoo import models, fields
from dateutil.relativedelta import relativedelta
import datetime
import calendar


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # Códigos de horas extra/recargos (se excluyen de la base de vacaciones)
    LIQ_EXTRA_CODES = ('HED', 'HEN', 'HRN', 'HEDDF', 'HRDDF', 'HENDF', 'HRNDF')

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _dias_comerciales(self):
        """Días del período en convención comercial (mes de 30), recortados al contrato.
        El último día del mes cuenta como día 30, así la 2Q da 15 en meses de 28, 30 o 31 días."""
        self.ensure_one()
        c = self.contract_id
        ini = self.date_from
        if c.date_start and c.date_start > ini:
            ini = c.date_start
        fin = self.date_to
        if c.date_end and c.date_end < fin:
            fin = c.date_end
        if not ini or not fin or fin < ini:
            return 0

        def dcom(d, es_fin):
            ult = calendar.monthrange(d.year, d.month)[1]
            if es_fin and d.day >= ult:
                return 30
            return min(d.day, 30)

        if ini.year == fin.year and ini.month == fin.month:
            return max(dcom(fin, True) - dcom(ini, False) + 1, 0)
        # períodos multi-mes (raro en quincenal): fallback a días calendario
        return (fin - ini).days + 1

    def _dias_cotizados_pila(self):
        """Días cotizados para PILA = días comerciales menos los días NO pagados."""
        self.ensure_one()
        base = self._dias_comerciales()
        nopag = sum(wd.number_of_days for wd in self.worked_days_line_ids if not wd.is_paid)
        return max(int(round(base - nopag)), 0)

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
    # Vacaciones disfrutadas (separar del básico para la nómina electrónica)
    # ------------------------------------------------------------------
    # Código de la entrada de trabajo / tipo de ausencia de vacaciones
    VAC_WE_CODE = '5'

    def _es_vacacion_we(self, wet):
        if not wet:
            return False
        code = (wet.code or '').strip()
        name = (wet.name or '').lower()
        return code == self.VAC_WE_CODE or 'vacacion' in name

    def _es_vacacion_leave(self, leave):
        st = leave.holiday_status_id
        if not st:
            return False
        name = (st.name or '').lower()
        wet = getattr(st, 'work_entry_type_id', False)
        code = (wet.code or '').strip() if wet else ''
        return 'vacacion' in name or code == self.VAC_WE_CODE

    def _vac_disfrutadas(self):
        """Días de vacaciones del período.
        - total: días calendario de vacaciones que caen dentro del período (se RESTAN del básico).
        - pagar: días de vacaciones a PAGAR en este período. Como el pago es anticipado (todo
          en el período donde inicia la vacación), 'pagar' = días completos de las ausencias que
          INICIAN dentro de este período; si la vacación empezó en un período anterior, es 0
          (ya se pagó) y solo restan del básico.
        - habiles / no_habiles: desglose de 'total' (para el reporte DIAN)."""
        self.ensure_one()
        habiles_we = sum(wd.number_of_days for wd in self.worked_days_line_ids
                         if self._es_vacacion_we(wd.work_entry_type_id))
        total = 0
        habiles_cal = 0
        pagar = 0
        if self.date_from and self.date_to:
            leaves = self.env['hr.leave'].search([
                ('employee_id', '=', self.employee_id.id),
                ('request_date_from', '<=', self.date_to),
                ('request_date_to', '>=', self.date_from),
                ('state', '=', 'validate'),
            ])
            for lv in leaves:
                if not self._es_vacacion_leave(lv):
                    continue
                # días dentro del período (para restar del básico)
                d1 = max(lv.request_date_from, self.date_from)
                d2 = min(lv.request_date_to, self.date_to)
                dd = d1
                while dd <= d2:
                    total += 1
                    if dd.weekday() < 5:
                        habiles_cal += 1
                    dd += datetime.timedelta(days=1)
                # pago anticipado: solo si la vacación INICIA en este período, se pagan
                # todos sus días (aunque se extiendan a quincenas siguientes)
                if self.date_from <= lv.request_date_from <= self.date_to:
                    dd = lv.request_date_from
                    while dd <= lv.request_date_to:
                        pagar += 1
                        dd += datetime.timedelta(days=1)
        habiles = round(habiles_we) if habiles_we else habiles_cal
        total = max(total, habiles)
        no_habiles = max(total - habiles, 0)
        return {'habiles': habiles, 'no_habiles': no_habiles, 'total': total, 'pagar': pagar}

    def _vac_valor_disfrutadas(self):
        """Valor a pagar por vacaciones disfrutadas = base de vacaciones / 30 x días."""
        return self._liq_base('vac') / 30.0 * self._vac_disfrutadas()['total']

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

    def _liq_vacaciones_compensadas(self, dias):
        """Valor de vacaciones compensadas en dinero: base de vacaciones / 30 x días.
        La base es el promedio del último año, sin horas extra ni auxilio de transporte."""
        return self._liq_base('vac') / 30.0 * (dias or 0.0)

    # ------------------------------------------------------------------
    # Indemnización por despido sin justa causa (Art. 64 CST)
    # ------------------------------------------------------------------
    def _liq_tiene_sinjusta(self):
        """True si el recibo tiene la entrada de 'sin justa causa'. La reconoce por el
        código (SINJUSTA) o por el nombre del tipo de entrada (contiene 'justa')."""
        for il in self.input_line_ids:
            code = (il.code or '').upper()
            nm = ''
            it = getattr(il, 'input_type_id', False)
            if it:
                nm = (it.name or '').upper()
            if 'SINJUSTA' in code or 'JUSTA' in code or 'JUSTA' in nm:
                return True
        return False

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
        if not self._liq_tiene_sinjusta():
            return 0.0
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
