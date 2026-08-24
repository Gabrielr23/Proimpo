# -*- coding: utf-8 -*-
"""Nómina electrónica DIAN (solución propia).

Genera el contenido del Documento Soporte de Pago de Nómina Electrónica
(NominaIndividual, tipo 102) desde el recibo, agrupando devengados y deducciones
por su categoría DIAN (la misma que ya usan las earn.line/deduction.line de Jorels),
calcula el CUNE (SHA-384) y deja el XML listo para firmar/transmitir con el motor
nativo l10n_co_dian.

Iteración 1: extracción de datos + XML base + CUNE. La firma/transmisión y el ajuste
fino del esquema se enganchan en el siguiente paso, validando contra la habilitación DIAN.
"""
from hashlib import sha384
from odoo import models, fields, api, _


# Categorías earn.line (Jorels) -> grupo de devengado DIAN
_EARN_GROUP = {
    'basic': 'basico',
    'transports_assistance': 'transporte', 'transports_viatic': 'transporte',
    'transports_non_salary_viatic': 'transporte',
    'daily_overtime': 'hora_extra', 'overtime_night_hours': 'hora_extra',
    'hours_night_surcharge': 'hora_extra', 'sunday_holiday_daily_overtime': 'hora_extra',
    'daily_surcharge_hours_sundays_holidays': 'hora_extra',
    'sunday_night_overtime_holidays': 'hora_extra',
    'sunday_holidays_night_surcharge_hours': 'hora_extra',
    'commissions': 'comision',
    'bonuses': 'bonif_salarial', 'bonuses_non_salary': 'bonif_no_salarial',
    'vacation_common': 'vacaciones', 'vacation_compensated': 'vacaciones_comp',
    'primas': 'prima', 'primas_non_salary': 'prima_no_salarial',
    'layoffs': 'cesantias', 'layoffs_interest': 'cesantias_interes',
    'incapacities_common': 'incap_comun', 'incapacities_professional': 'incap_prof',
    'incapacities_working': 'incap_laboral',
    'licensings_maternity_or_paternity_leaves': 'lic_maternidad',
    'licensings_permit_or_paid_licenses': 'lic_remunerada',
    'licensings_suspension_or_unpaid_leaves': 'lic_no_remunerada',
    'assistances': 'auxilio', 'assistances_non_salary': 'auxilio_no_salarial',
    'other_concepts': 'otro_concepto', 'other_concepts_non_salary': 'otro_concepto_no_salarial',
    'legal_strikes': 'huelga', 'refund': 'reintegro',
    'compensations_ordinary': 'compensacion', 'compensations_extraordinary': 'compensacion',
    'company_withdrawal_bonus': 'bonif_retiro', 'endowment': 'dotacion',
}

# Códigos de deducción (deduction_category) -> grupo DIAN
_DED_GROUP = {
    'health': 'salud', 'pension': 'pension',
    'fund': 'fondo_sp', 'fsp': 'fondo_sp', 'solidarity': 'fondo_sp_solidaridad',
    'withholding': 'retencion_fuente', 'rtf': 'retencion_fuente',
    'afc': 'afc', 'voluntary_pension': 'pension_voluntaria',
    'libranzas': 'libranza', 'advances': 'anticipo',
    'other_deductions': 'otra_deduccion', 'loan': 'libranza',
}


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    ne_xml = fields.Text(string="XML Nómina Electrónica", copy=False, readonly=True)
    ne_cune = fields.Char(string="CUNE", copy=False, readonly=True)
    ne_state = fields.Selection([
        ('draft', 'Borrador'), ('generated', 'Generado'),
        ('sent', 'Enviado'), ('accepted', 'Aceptado'), ('rejected', 'Rechazado'),
    ], string="Estado NE", default='draft', copy=False)

    # ------------------------------------------------------------------
    # Agrupación de devengados / deducciones por concepto DIAN
    # ------------------------------------------------------------------
    def _ne_group_earn(self):
        """Devuelve {grupo_dian: [{'concepto','codigo','cantidad','valor', earn}]}"""
        self.ensure_one()
        out = {}
        for e in self.earn_ids:
            if not e.total:
                continue
            grupo = _EARN_GROUP.get(e.category, 'otro_concepto')
            out.setdefault(grupo, []).append({
                'concepto': e.name or '', 'codigo': e.code or '', 'categoria': e.category,
                'cantidad': abs(e.quantity or 0.0), 'valor': abs(e.total),
                'date_start': e.date_start, 'date_end': e.date_end,
                'time_start': e.time_start, 'time_end': e.time_end,
            })
        return out

    def _ne_group_deduction(self):
        self.ensure_one()
        out = {}
        for d in self.line_ids.filtered(lambda l: l.salary_rule_id.type_concept == 'deduction' and l.total):
            cat = (getattr(d.salary_rule_id, 'deduction_category', '') or '').lower()
            grupo = _DED_GROUP.get(cat) or _DED_GROUP.get((d.salary_rule_id.code or '').lower(), 'otra_deduccion')
            out.setdefault(grupo, []).append({
                'concepto': d.name or '', 'codigo': d.salary_rule_id.code or '',
                'valor': abs(d.total),
            })
        return out

    # ------------------------------------------------------------------
    # Datos del documento (todas las secciones)
    # ------------------------------------------------------------------
    def _ne_datos(self):
        self.ensure_one()
        e = self.employee_id
        ct = self.contract_id
        company = self.company_id
        devengados = self._ne_group_earn()
        deducciones = self._ne_group_deduction()
        dev_total = sum(sum(i['valor'] for i in v) for v in devengados.values())
        ded_total = sum(sum(i['valor'] for i in v) for v in deducciones.values())
        nit, dv = self._ne_nit_dv(company)
        return {
            'tipo_documento': '102',                       # NominaIndividual
            'periodo': {'inicio': self.date_from, 'fin': self.date_to},
            'numero': self.number or '',
            'empleador': {
                'nit': nit, 'dv': dv,
                'razon_social': company.name,
                'pais': 'CO', 'municipio': company.city or '',
            },
            'trabajador': {
                'tipo_doc': self._ne_tipo_doc(e),
                'numero_doc': e.identification_id or '',
                'primer_apellido': self._ne_nombre(e, 'ap1'),
                'segundo_apellido': self._ne_nombre(e, 'ap2'),
                'primer_nombre': self._ne_nombre(e, 'no1'),
                'otros_nombres': self._ne_nombre(e, 'no2'),
                'tipo_trabajador': (ct.type_worker_id.code if ct and ct.type_worker_id else '01'),
                'salario': ct.wage if ct else 0.0,
                'sueldo_integral': 'true' if (ct and ct.integral_salary) else 'false',
            },
            'pago': {
                'forma': 'Efectivo' if not e.bank_account_id else 'Transferencia',
                'banco': e.bank_account_id.bank_id.name if e.bank_account_id else '',
                'cuenta': e.bank_account_id.acc_number if e.bank_account_id else '',
            },
            'devengados': devengados,
            'deducciones': deducciones,
            'devengados_total': round(dev_total, 2),
            'deducciones_total': round(ded_total, 2),
            'comprobante_total': round(dev_total - ded_total, 2),
        }

    @staticmethod
    def _ne_tipo_doc(emp):
        code = (getattr(emp, 'l10n_latam_document_type_id', False) and
                emp.l10n_latam_document_type_id.l10n_co_document_code) or 'cc'
        return {'cc': '13', 'ce': '22', 'ti': '12', 'pa': '41', 'nit': '31'}.get(str(code).lower(), '13')

    @staticmethod
    def _ne_nombre(emp, parte):
        nombre = (emp.name or '').strip().upper()
        if ',' in nombre:
            ape, nom = nombre.split(',', 1)
        else:
            ps = nombre.split()
            ape = ' '.join(ps[:2]); nom = ' '.join(ps[2:])
        ape = ape.split(); nom = nom.split()
        return {'ap1': ape[0] if ape else '', 'ap2': ' '.join(ape[1:]) if len(ape) > 1 else '',
                'no1': nom[0] if nom else '', 'no2': ' '.join(nom[1:]) if len(nom) > 1 else ''}.get(parte, '')

    def _ne_nit_dv(self, company):
        """Devuelve (NIT sin DV, DV) del empleador, reutilizando los helpers del
        motor nativo l10n_co para garantizar que el NIT NO lleve el dígito de
        verificación pegado (causa típica del rechazo 'no corresponde al participante')."""
        partner = company.partner_id
        try:
            nit = partner._get_vat_without_verification_code()
            dv = partner._get_vat_verification_code()
            if nit:
                return ''.join(c for c in nit if c.isdigit()), dv
        except Exception:
            pass
        raw = ''.join(c for c in (company.vat or '') if c.isdigit())
        # Si el vat trae DV pegado (10 dígitos para NIT de 9), se separa el último.
        if len(raw) == 10:
            return raw[:9], raw[9]
        return raw, self._ne_dv(raw)

    @staticmethod
    def _ne_dv(nit):
        """Dígito de verificación del NIT (algoritmo DIAN)."""
        pesos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
        n = ''.join(ch for ch in str(nit or '') if ch.isdigit())
        if not n:
            return '0'
        s = sum(int(d) * pesos[i] for i, d in enumerate(reversed(n)))
        r = s % 11
        return str(r if r < 2 else 11 - r)

    def _ne_qr_url(self, cune):
        base = ('https://catalogo-vpfe-hab.dian.gov.co' if self.company_id.l10n_co_dian_test_environment
                else 'https://catalogo-vpfe.dian.gov.co')
        return '%s/document/searchqr?documentkey=%s' % (base, cune)

    # ------------------------------------------------------------------
    # CUNE (SHA-384) — Anexo Técnico Nómina Electrónica
    # ------------------------------------------------------------------
    def _ne_cune(self, datos, software_pin=''):
        """CUNE = SHA384 de la cadena: NumNE + FecNE + HoraNE + ValorDevengado +
        ValorDeducciones + ValorTotal + NitNE + DocEmpleado + TipoXML + SoftwarePin + AmbienteNE."""
        self.ensure_one()
        amb = '2' if self.company_id.l10n_co_dian_test_environment else '1'
        cadena = '{num}{fec}{hora}{dev:.2f}{ded:.2f}{tot:.2f}{nit}{doc}{tipo}{pin}{amb}'.format(
            num=datos['numero'], fec=str(self.date_to or ''), hora='00:00:00-05:00',
            dev=datos['devengados_total'], ded=datos['deducciones_total'], tot=datos['comprobante_total'],
            nit=datos['empleador']['nit'], doc=datos['trabajador']['numero_doc'],
            tipo=datos['tipo_documento'], pin=software_pin, amb=amb)
        return sha384(cadena.encode()).hexdigest()

    def _ne_build_xml(self, datos, cune, op_mode=None, software_sc=''):
        """Arma el XML NominaIndividual.

        La firma XAdES (ext:UBLExtensions) se inserta aparte en hr_payslip_ne_dian.py.
        El esquema de elementos se afina de forma iterativa contra el validador DIAN
        (mismo enfoque que usamos con la PILA)."""
        from lxml import etree
        NS = "dian:gov:co:facturaelectronica:NominaIndividual"
        nsmap = {
            None: NS,
            'ext': "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
            'ds': "http://www.w3.org/2000/09/xmldsig#",
            'xades': "http://uri.etsi.org/01903/v1.3.2#",
        }
        root = etree.Element('{%s}NominaIndividual' % NS, nsmap=nsmap)
        nit = datos['empleador']['nit']
        dv = datos['empleador'].get('dv') or self._ne_dv(nit)

        def sub(parent, tag, _text=None, **attrs):
            el = etree.SubElement(parent, '{%s}%s' % (NS, tag))
            if _text is not None:
                el.text = str(_text)
            for k, v in attrs.items():
                el.set(k, str(v))
            return el

        sub(root, 'Periodo', FechaIngreso=str(datos['periodo']['inicio'] or ''),
            FechaLiquidacionInicio=str(datos['periodo']['inicio'] or ''),
            FechaLiquidacionFin=str(datos['periodo']['fin'] or ''))
        sub(root, 'NumeroSecuenciaXML', Numero=datos['numero'])
        sub(root, 'LugarGeneracion', Pais='CO', DepartamentoEstado='',
            MunicipioCiudad=datos['empleador']['municipio'], Idioma='es')
        # Proveedor tecnológico = la propia empresa (software propio)
        if op_mode is not None:
            sub(root, 'ProveedorXML', NIT=nit, DV=dv, SoftwareID=op_mode.dian_software_id or '',
                SoftwareSC=software_sc or '')
        sub(root, 'CodigoQR', _text=self._ne_qr_url(cune))
        sub(root, 'InformacionGeneral', Version='V1.0: Documento Soporte de Pago de Nómina Electrónica',
            TipoXML=datos['tipo_documento'], CUNE=cune, EncripCUNE='CUNE-SHA384',
            Ambiente=('2' if self.company_id.l10n_co_dian_test_environment else '1'),
            PeriodoNomina='5', TipoMoneda='COP', FechaGen=str(datos['periodo']['fin'] or ''))
        emp = sub(root, 'Empleador', NIT=nit, DV=dv, RazonSocial=datos['empleador']['razon_social'],
                  Pais=datos['empleador']['pais'])
        tr = sub(root, 'Trabajador', TipoTrabajador=datos['trabajador']['tipo_trabajador'],
                 TipoDocumento=datos['trabajador']['tipo_doc'], NumeroDocumento=datos['trabajador']['numero_doc'],
                 PrimerApellido=datos['trabajador']['primer_apellido'], SegundoApellido=datos['trabajador']['segundo_apellido'],
                 PrimerNombre=datos['trabajador']['primer_nombre'], OtrosNombres=datos['trabajador']['otros_nombres'],
                 Sueldo='%.2f' % datos['trabajador']['salario'], SalarioIntegral=datos['trabajador']['sueldo_integral'])
        # Devengados
        dev = sub(root, 'Devengados')
        for grupo, items in datos['devengados'].items():
            for it in items:
                sub(dev, 'Devengado', Concepto=it['concepto'], Grupo=grupo,
                    Cantidad='%.2f' % it['cantidad'], Pago='%.2f' % it['valor'])
        # Deducciones
        ded = sub(root, 'Deducciones')
        for grupo, items in datos['deducciones'].items():
            for it in items:
                sub(ded, 'Deduccion', Concepto=it['concepto'], Grupo=grupo, Valor='%.2f' % it['valor'])
        # Totales
        sub(root, 'ComprobanteTotal', DevengadosTotal='%.2f' % datos['devengados_total'],
            DeduccionesTotal='%.2f' % datos['deducciones_total'], ComprobanteTotal='%.2f' % datos['comprobante_total'])
        return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='UTF-8').decode()
