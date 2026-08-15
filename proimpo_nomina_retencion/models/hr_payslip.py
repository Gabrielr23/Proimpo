# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # --- Almacenamiento de la depuración (para el reporte de auditoría) ---
    rtf_proyectada = fields.Boolean(string="Retención proyectada (1Q)")
    # 1. Ingresos
    rtf_1_ingresos = fields.Monetary(string="1. Ingresos brutos")
    # 2. INCRNGO
    rtf_2_pension = fields.Monetary(string="Pensión + FSP obligatoria")
    rtf_2_salud = fields.Monetary(string="Salud obligatoria")
    rtf_2_incrngo = fields.Monetary(string="2.1 Subtotal INCRNGO")
    rtf_2_neto = fields.Monetary(string="2.2 Ingresos netos")
    # 3. Deducciones Art. 387
    rtf_3_medicina = fields.Monetary(string="Medicina prepagada")
    rtf_3_dependientes = fields.Monetary(string="Dependientes")
    rtf_3_vivienda = fields.Monetary(string="Intereses de vivienda")
    rtf_3_deducibles = fields.Monetary(string="3.2 Total deducibles")
    rtf_3_subtotal = fields.Monetary(string="3.3 Subtotal")
    # 4. Rentas exentas
    rtf_4_exentas = fields.Monetary(string="4.1 Rentas exentas (AFC/vol.)")
    rtf_4_gravable = fields.Monetary(string="4.2 Subtotal gravable")
    rtf_4_25exento = fields.Monetary(string="4.3 25% exento")
    rtf_4_subtotal = fields.Monetary(string="4.4 Subtotal")
    # 5. Excedente (límite 40%)
    rtf_5_deducciones = fields.Monetary(string="5.1 Total deducciones")
    rtf_5_limite40 = fields.Monetary(string="5.2 Límite 40%")
    rtf_5_excedente = fields.Monetary(string="5.3 Base excedente")
    rtf_5_base = fields.Monetary(string="5.4 Base líquida gravable")
    # 6. Retención
    rtf_6_base_uvt = fields.Float(string="6.1 Base en UVT", digits=(16, 2))
    rtf_6_ret_uvt = fields.Float(string="6.2 Retención en UVT", digits=(16, 2))
    rtf_6_retencion_mes = fields.Monetary(string="Retención del mes")
    rtf_6_ya_retenido = fields.Monetary(string="Menos valores descontados (1Q)")
    rtf_6_valor = fields.Monetary(string="Retención del período")
    # Valores reales del período (para que la 2Q sume el mes)
    rtf_periodo_salarial = fields.Monetary(string="Base salarial del período")
    rtf_periodo_nosal = fields.Monetary(string="Bonos no salariales del período")
    rtf_ytd_exento25 = fields.Monetary(string="Acum. 25% exento del año (tope 790 UVT)")
    rtf_ytd_deducciones = fields.Monetary(string="Acum. deducciones+exentas del año (tope 1.340 UVT)")

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _proimpo_line(self, code):
        """Total de una regla salarial (por código) en este recibo."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.salary_rule_id.code == code)
        return sum(lines.mapped('total'))

    def _proimpo_slip_1q(self):
        """Recibo de la primera quincena del mismo mes (para el ajuste de 2Q)."""
        self.ensure_one()
        if not self.date_from:
            return self.env['hr.payslip']
        primero = self.date_from.replace(day=1)
        return self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '>=', primero),
            ('date_from', '<', self.date_from),
            ('state', 'in', ('done', 'paid')),
            ('id', '!=', self.id),
        ], order='date_from desc', limit=1)

    def _rtf_ytd(self, campo):
        """Acumulado del campo de depuracion en los MESES anteriores del año (para el
        control anual de topes: 790 UVT del 25% exento y 1.340 UVT del total). De cada
        mes anterior toma el valor real (ultimo recibo del mes, es decir la 2Q)."""
        self.ensure_one()
        if not self.date_from:
            return 0.0
        anio_ini = self.date_from.replace(month=1, day=1)
        mes_ini = self.date_from.replace(day=1)
        prev = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id),
            ('date_from', '>=', anio_ini),
            ('date_from', '<', mes_ini),
        ])
        por_mes = {}
        for pr in prev:
            k = pr.date_from.month
            cur = por_mes.get(k)
            if cur is None or (pr.date_from, pr.id) > (cur.date_from, cur.id):
                por_mes[k] = pr
        return sum((pr[campo] or 0.0) for pr in por_mes.values())

    @staticmethod
    def _proimpo_tabla_383(base_uvt):
        """Tabla del Art. 383 E.T. Devuelve la retención expresada en UVT."""
        b = base_uvt
        if b <= 95:
            return 0.0
        elif b <= 150:
            return (b - 95) * 0.19
        elif b <= 360:
            return (b - 150) * 0.28 + 10
        elif b <= 640:
            return (b - 360) * 0.33 + 69
        elif b <= 945:
            return (b - 640) * 0.35 + 162
        elif b <= 2300:
            return (b - 945) * 0.37 + 268
        else:
            return (b - 2300) * 0.39 + 770

    @staticmethod
    def _proimpo_cfield(contract, name):
        return getattr(contract, name, 0) or 0

    # ------------------------------------------------------------------
    # Depuración de retención (Procedimiento 1) - replica reporte CGUNO
    # ------------------------------------------------------------------
    @staticmethod
    def _proimpo_fsp_pct(ibc, smmlv):
        """Porcentaje del Fondo de Solidaridad Pensional según el IBC."""
        r = (ibc / smmlv) if smmlv else 0.0
        if 4 <= r < 16:
            return 0.010
        elif 16 <= r < 17:
            return 0.012
        elif 17 <= r < 18:
            return 0.014
        elif 18 <= r < 19:
            return 0.016
        elif 19 <= r < 20:
            return 0.018
        elif r >= 20:
            return 0.020
        return 0.0

    def _proimpo_rtf(self, basico=0.0, devsal=0.0, devnosal=0.0):
        """Calcula la retención del período, almacena la depuración y devuelve el valor.

        Recibe desde la regla RTF: básico, DEVSAL (devengado salarial: comisiones,
        extras, bonos salariales) y DEVNOSAL (devengado no salarial). De DEVNOSAL se
        excluye el auxilio de rodamiento (estimado desde el contrato); el resto son
        bonificaciones no salariales, que SÍ son ingreso gravable para retención.

        Base de ingresos = básico + devengado salarial + bonos no salariales.
        Se excluyen los auxilios de transporte y rodamiento (no son ingreso gravable).

        Ley 1393: si los pagos no salariales superan el 40% de la remuneración total,
        el exceso se suma al IBC (sube salud/pensión).

        Proyección 1Q = básico real de la 1Q + una segunda quincena completa; las
        variables se proyectan x2. En 2Q se toma el real del mes (1Q + 2Q, leyendo los
        valores guardados de la 1Q) y se descuenta lo ya retenido en la 1Q.
        """
        self.ensure_one()
        contract = self.contract_id
        company = contract.company_id
        uvt = company.uvt_value or 0.0
        smmlv = company.smmlv_value or 0.0
        if not uvt or not contract:
            return 0.0

        # Valores del período actual (recibidos desde la regla)
        basico = basico or 0.0
        devsal = devsal or 0.0
        devnosal = devnosal or 0.0
        cap = 25.0 * smmlv

        # Separar el rodamiento (auxilio, se excluye) de las bonificaciones no salariales
        dia_val = contract.wage / 30.0
        dias_pag = (basico / dia_val) if dia_val else 0.0
        rod = self._proimpo_cfield(contract, 'x_studio_auxilio_de_rodamiento') / 30.0 * dias_pag
        salarial_periodo = basico + devsal
        bonos_periodo = max(devnosal - rod, 0.0)

        def _aportes(base_ibc):
            b = min(base_ibc, cap) if base_ibc > 0 else 0.0
            s = b * 0.04
            p = b * 0.04 + b * self._proimpo_fsp_pct(b, smmlv)
            return s, p

        def _base_1393(salarial, bonos):
            # Ley 1393: exceso de no salariales sobre el 40% del total se vuelve IBC
            total = salarial + bonos
            exceso = max(bonos - 0.40 * total, 0.0)
            return salarial + exceso

        es_1q = self.date_from and self.date_from.day <= 15

        if es_1q:
            # Proyección: básico real de la 1Q + segunda quincena completa
            seg = contract.wage / 2.0
            if (contract.date_end and contract.date_end.year == self.date_from.year
                    and contract.date_end.month == self.date_from.month):
                d = contract.date_end.day
                seg = 0.0 if d <= 15 else contract.wage / 30.0 * min(d - 15, 15)
            # Salario y comisiones (recurrentes) se proyectan al mes (x2 la quincena).
            salarial_proy = (basico + seg) + devsal * 2.0
            # Bonificaciones NO salariales: NO se proyectan. Por el OTROSI se pagan
            # una sola vez (1Q), asi que se gravan tal como se reciben, sin x2.
            bonos_proy = bonos_periodo
            ingreso = salarial_proy + bonos_proy
            base_ibc = _base_1393(salarial_proy, bonos_proy)
            incr_salud, incr_pension = _aportes(base_ibc)
            ya_retenido = 0.0
            proyectada = True
        else:
            # 2Q: real del mes = período actual + 1Q (valores guardados)
            slip1 = self._proimpo_slip_1q()
            sal_1q = bon_1q = r1 = 0.0
            if slip1:
                sal_1q = slip1.rtf_periodo_salarial or slip1._proimpo_line('IBC')
                bon_1q = slip1.rtf_periodo_nosal
                r1 = abs(slip1._proimpo_line('RTF'))
            salarial_mes = salarial_periodo + sal_1q
            bonos_mes = bonos_periodo + bon_1q
            ingreso = salarial_mes + bonos_mes
            base_ibc = _base_1393(salarial_mes, bonos_mes)
            incr_salud, incr_pension = _aportes(base_ibc)
            ya_retenido = r1
            proyectada = False

        # Campos del contrato (valores mensuales fijos)
        afc = self._proimpo_cfield(contract, 'x_studio_aportes_afc')
        vol = self._proimpo_cfield(contract, 'x_studio_aporte_fondo_voluntario_de_pensiones')
        medicina = self._proimpo_cfield(contract, 'x_studio_medicina_prepagada')
        vivienda = self._proimpo_cfield(contract, 'x_studio_intereses_de_vivienda')
        dep = str(getattr(contract, 'x_studio_dependientes', '') or '').upper()
        tiene_dep = 'SI' in dep or 'SÍ' in dep

        # === 1. INGRESOS BRUTOS ===
        ingresos_brutos = ingreso
        # === 2. INCRNGO (aportes obligatorios) ===
        incrngo = incr_salud + incr_pension
        ingreso_neto = ingresos_brutos - incrngo
        # === 3. DEDUCCIONES (Art. 387) - topes mensuales ===
        ded_medicina = min(medicina, 16 * uvt)
        ded_dependientes = min(ingresos_brutos * 0.10, 32 * uvt) if tiene_dep else 0.0
        ded_vivienda = min(vivienda, 100 * uvt)
        total_deducibles = ded_medicina + ded_dependientes + ded_vivienda
        subtotal_3 = ingreso_neto - total_deducibles
        # === 4. RENTAS EXENTAS ===
        exentas = min(afc + vol, ingresos_brutos * 0.30, 3800 * uvt / 12.0)
        gravable = subtotal_3 - exentas
        # 25% exento (Art. 206-10). El tope de 790 UVT es ANUAL (Ley 2277) y se
        # controla al totalizar el ano; en la retencion mensual no se prorratea.
        # El 40% (paso 5) ya limita el total de exentas + deducciones del mes.
        exento_25 = gravable * 0.25
        # Tope ANUAL acumulado de 790 UVT (Ley 2277): se concede el 25% hasta agotar
        # 790 UVT sumando lo ya concedido en meses anteriores del año (tu fila 44).
        ytd_25 = self._rtf_ytd('rtf_4_25exento')
        exento_25 = min(exento_25, max(790.0 * uvt - ytd_25, 0.0))
        subtotal_4 = gravable - exento_25
        # === 5. EXCEDENTE (límite 40%, Art. 336) ===
        total_deducciones = total_deducibles + exentas + exento_25
        # Limite del 40% (Art. 388). Las 1.340 UVT son tope ANUAL (Art. 336,
        # Ley 2277), se controlan al totalizar el ano, no mes a mes.
        limite_40 = ingreso_neto * 0.40
        # Tope ANUAL acumulado de 1.340 UVT sobre deducciones + rentas exentas.
        ytd_total = self._rtf_ytd('rtf_5_deducciones')
        tope_1340 = max(1340.0 * uvt - ytd_total, 0.0)
        limite_efectivo = min(limite_40, tope_1340)
        excedente = max(total_deducciones - limite_efectivo, 0.0)
        base = subtotal_4 + excedente
        # === 6. RETENCIÓN (tabla Art. 383) ===
        base_uvt = base / uvt if uvt else 0.0
        ret_uvt = self._proimpo_tabla_383(base_uvt)
        retencion_mes = round(ret_uvt * uvt / 1000.0) * 1000.0  # redondeo a miles (CGUNO)
        valor = max(retencion_mes - ya_retenido, 0.0) if not es_1q else retencion_mes

        # Almacenar depuración para el reporte
        self.write({
            'rtf_proyectada': proyectada,
            'rtf_1_ingresos': ingresos_brutos,
            'rtf_2_pension': incr_pension,
            'rtf_2_salud': incr_salud,
            'rtf_2_incrngo': incrngo,
            'rtf_2_neto': ingreso_neto,
            'rtf_3_medicina': ded_medicina,
            'rtf_3_dependientes': ded_dependientes,
            'rtf_3_vivienda': ded_vivienda,
            'rtf_3_deducibles': total_deducibles,
            'rtf_3_subtotal': subtotal_3,
            'rtf_4_exentas': exentas,
            'rtf_4_gravable': gravable,
            'rtf_4_25exento': exento_25,
            'rtf_4_subtotal': subtotal_4,
            'rtf_5_deducciones': total_deducciones,
            'rtf_5_limite40': limite_40,
            'rtf_5_excedente': excedente,
            'rtf_5_base': base,
            'rtf_6_base_uvt': base_uvt,
            'rtf_6_ret_uvt': ret_uvt,
            'rtf_6_retencion_mes': retencion_mes,
            'rtf_6_ya_retenido': ya_retenido,
            'rtf_6_valor': valor,
            'rtf_periodo_salarial': salarial_periodo,
            'rtf_periodo_nosal': bonos_periodo,
            'rtf_ytd_exento25': ytd_25 + exento_25,
            'rtf_ytd_deducciones': ytd_total + total_deducciones,
        })
        return valor
