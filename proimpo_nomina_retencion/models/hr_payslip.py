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

    def _proimpo_rtf(self, gross=0.0, basico=0.0, ibc=0.0, devsal=0.0):
        """Calcula la retención del período, almacena la depuración y devuelve el valor.

        Recibe desde la regla RTF los valores del período actual: gross, básico, IBC y
        DEVSAL (devengado salarial: comisiones, extras, bonos salariales). Salud (4%),
        pensión (4%) y FSP se calculan internamente desde el IBC proyectado, para no
        depender de reglas condicionales (FSP) que pueden no estar definidas.

        Base de retención = ingreso salarial (básico + devengado salarial). Se excluyen
        los auxilios de transporte y de rodamiento (no son ingreso para retención).

        Proyección 1Q = básico real de la 1Q + una segunda quincena completa; las
        variables salariales se proyectan x2. En 2Q se toma el real del mes (1Q + 2Q)
        y se descuenta lo ya retenido en la 1Q.
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
        ibc = ibc or 0.0
        devsal = devsal or 0.0
        cap = 25.0 * smmlv

        def _aportes(base_ibc):
            b = min(base_ibc, cap) if base_ibc > 0 else 0.0
            s = b * 0.04
            p = b * 0.04 + b * self._proimpo_fsp_pct(b, smmlv)
            return s, p

        es_1q = self.date_from and self.date_from.day <= 15

        if es_1q:
            # Proyección: básico real de la 1Q + segunda quincena completa
            seg = contract.wage / 2.0
            if (contract.date_end and contract.date_end.year == self.date_from.year
                    and contract.date_end.month == self.date_from.month):
                d = contract.date_end.day
                seg = 0.0 if d <= 15 else contract.wage / 30.0 * min(d - 15, 15)
            salario_proy = basico + seg
            base_ibc = salario_proy + devsal * 2.0
            ingreso = base_ibc
            incr_salud, incr_pension = _aportes(base_ibc)
            ya_retenido = 0.0
            proyectada = True
        else:
            # 2Q: real del mes = base salarial 1Q + 2Q; se descuenta lo retenido en 1Q
            slip1 = self._proimpo_slip_1q()
            base_1q = r1 = 0.0
            if slip1:
                base_1q = slip1._proimpo_line('IBC')
                r1 = abs(slip1._proimpo_line('RTF'))
            base_ibc = (basico + devsal) + base_1q
            ingreso = base_ibc
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
        exento_25 = min(gravable * 0.25, 790 * uvt / 12.0)
        subtotal_4 = gravable - exento_25
        # === 5. EXCEDENTE (límite 40%, Art. 336) ===
        total_deducciones = total_deducibles + exentas + exento_25
        limite_40 = min(ingreso_neto * 0.40, 1340 * uvt / 12.0)
        excedente = max(total_deducciones - limite_40, 0.0)
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
        })
        return valor
