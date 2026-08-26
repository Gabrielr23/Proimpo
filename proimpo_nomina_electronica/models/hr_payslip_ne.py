# -*- coding: utf-8 -*-
"""Nómina electrónica DIAN (solución propia) — generador del XML NominaIndividual.

La estructura se replica 1:1 de un XML real de PROIMPO ya aceptado por la DIAN
(patrón de oro generado por SIESA): mismos elementos, atributos, orden y códigos.
Documento Soporte de Pago de Nómina Electrónica, tipo 102 (y 103 de ajuste).
"""
from datetime import datetime, timezone, timedelta
from hashlib import sha384
from odoo import models, fields, api, _

NS = "dian:gov:co:facturaelectronica:NominaIndividual"
NS_EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"
NS_XADES141 = "http://uri.etsi.org/01903/v1.4.1#"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# Valores de ubicación del EMPLEADOR (PROIMPO) — reales, ya aceptados por la DIAN.
_EMPLEADOR_DEF = {'depto': '76', 'muni': '76892', 'dir': 'CL 15 27 A 176 BL 7 BD 2'}

# earn.line.category (Jorels) -> (bucket, atributo).  Buckets con estructura propia
# se manejan aparte (vacaciones, primas, cesantías, bonif, auxilios, comisiones...).
_DEV_SIMPLE = {
    # Transporte
    'transports_assistance': ('transporte', 'AuxilioTransporte'),
    'transports_viatic': ('transporte', 'ViaticoManuAlojS'),
    'transports_non_salary_viatic': ('transporte', 'ViaticoManuAlojNS'),
}


def _money(v):
    return '%.2f' % (round(float(v or 0.0), 2))


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    ne_xml = fields.Text(string="XML Nómina Electrónica", copy=False, readonly=True)
    ne_cune = fields.Char(string="CUNE", copy=False, readonly=True)
    ne_state = fields.Selection([
        ('draft', 'Borrador'), ('generated', 'Generado'),
        ('sent', 'Enviado'), ('accepted', 'Aceptado'), ('rejected', 'Rechazado'),
    ], string="Estado NE", default='draft', copy=False)

    # ------------------------------------------------------------------
    # Sumas por concepto (usa earn.line.category y deduction_category)
    # ------------------------------------------------------------------
    def _earn_by_cat(self):
        """Devuelve {category: total} sumando earn.line por categoría DIAN."""
        self.ensure_one()
        out = {}
        for e in self.earn_ids:
            if not e.total:
                continue
            out[e.category] = out.get(e.category, 0.0) + abs(e.total)
        return out

    def _ded_lines(self):
        """Devuelve lista de (deduction_category, code, name, total) de deducciones."""
        self.ensure_one()
        res = []
        for d in self.line_ids.filtered(
                lambda l: l.salary_rule_id.type_concept == 'deduction' and l.total):
            cat = (getattr(d.salary_rule_id, 'deduction_category', '') or '').lower()
            res.append((cat, (d.salary_rule_id.code or '').lower(), d.name or '', abs(d.total)))
        return res

    # ------------------------------------------------------------------
    # Helpers de identidad / fechas / códigos
    # ------------------------------------------------------------------
    def _ne_nit_dv(self, company):
        partner = company.partner_id
        try:
            nit = partner._get_vat_without_verification_code()
            dv = partner._get_vat_verification_code()
            if nit:
                return ''.join(c for c in nit if c.isdigit()), str(dv)
        except Exception:
            pass
        raw = ''.join(c for c in (company.vat or '') if c.isdigit())
        if len(raw) == 10:
            return raw[:9], raw[9]
        return raw, self._ne_dv(raw)

    @staticmethod
    def _ne_dv(nit):
        pesos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
        n = ''.join(ch for ch in str(nit or '') if ch.isdigit())
        if not n:
            return '0'
        s = sum(int(d) * pesos[i] for i, d in enumerate(reversed(n)))
        r = s % 11
        return str(r if r < 2 else 11 - r)

    @staticmethod
    def _ne_tipo_doc(emp):
        code = (getattr(emp, 'l10n_latam_document_type_id', False) and
                emp.l10n_latam_document_type_id.l10n_co_document_code) or 'cc'
        return {'cc': '13', 'ce': '22', 'ti': '12', 'pa': '41', 'nit': '31',
                'rc': '11', 'pep': '47'}.get(str(code).lower(), '13')

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

    def _ne_ubicacion(self, partner, defecto):
        """(departamento DANE, municipio DANE, dirección). Cae a defaults de PROIMPO."""
        depto = muni = ''
        try:
            if partner.state_id and partner.state_id.code:
                depto = ''.join(c for c in partner.state_id.code if c.isdigit())[:2]
            city = getattr(partner, 'l10n_co_dian_municipality_id', False) or getattr(partner, 'city_id', False)
            if city and getattr(city, 'l10n_co_edi_code', False):
                muni = city.l10n_co_edi_code
        except Exception:
            pass
        return (depto or defecto['depto'], muni or defecto['muni'],
                (partner.street or '') or defecto['dir'])

    def _ne_periodo_nomina(self):
        """Código de periodo de nómina DIAN según duración: 3=quincenal, 4=mensual."""
        if self.date_from and self.date_to:
            dias = (self.date_to - self.date_from).days + 1
            if dias >= 27:
                return '4'
            if dias >= 14:
                return '3'
            if dias >= 8:
                return '2'
            return '1'
        return '4'

    def _ne_now(self):
        tz = timezone(timedelta(hours=-5))
        now = datetime.now(tz)
        return now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S-05:00')

    def _ne_dias_trabajados(self):
        dias = 0
        for wl in self.worked_days_line_ids:
            code = (wl.code or '').upper()
            if code in ('WORK100', 'WORK') or (wl.amount and 'work' in code.lower()):
                dias += wl.number_of_days
        if not dias and self.date_from and self.date_to:
            dias = min(30, (self.date_to - self.date_from).days + 1)
        return int(round(dias))

    # ------------------------------------------------------------------
    # Datos del documento
    # ------------------------------------------------------------------
    def _ne_datos(self):
        self.ensure_one()
        e = self.employee_id
        ct = self.contract_id
        company = self.company_id
        nit, dv = self._ne_nit_dv(company)
        e_depto, e_muni, e_dir = self._ne_ubicacion(company.partner_id, _EMPLEADOR_DEF)
        t_depto, t_muni, t_dir = self._ne_ubicacion(
            e.address_id or company.partner_id, {'depto': e_depto, 'muni': e_muni, 'dir': e_dir})
        fecha_gen, hora_gen = self._ne_now()

        earn = self._earn_by_cat()
        ded = self._ded_lines()
        dev_total, ded_total = self._ne_totales(earn, ded)

        # Prefijo + consecutivo del número del documento
        numero = (self.number or '').replace(' ', '').replace('-', '')
        prefijo = ''.join(c for c in numero if not c.isdigit())[:4] or 'NE'
        consecutivo = ''.join(c for c in numero if c.isdigit()) or str(self.id)
        numero_full = prefijo + consecutivo

        dias_trab = self._ne_dias_trabajados()
        tiempo_lab = dias_trab
        if ct and ct.date_start and self.date_to:
            tiempo_lab = max(0, (self.date_to - ct.date_start).days)

        return {
            'tipo_documento': '102',
            'ambiente': '2' if company.l10n_co_dian_test_environment else '1',
            'fecha_gen': fecha_gen, 'hora_gen': hora_gen,
            'periodo': {
                'ingreso': str(ct.date_start) if ct and ct.date_start else str(self.date_from or ''),
                'inicio': str(self.date_from or ''), 'fin': str(self.date_to or ''),
                'tiempo': str(tiempo_lab),
            },
            'periodo_nomina': self._ne_periodo_nomina(),
            'secuencia': {'prefijo': prefijo, 'consecutivo': consecutivo, 'numero': numero_full},
            'lugar': {'depto': e_depto, 'muni': e_muni},
            'empleador': {
                'razon_social': company.name, 'nit': nit, 'dv': dv,
                'depto': e_depto, 'muni': e_muni, 'dir': e_dir,
            },
            'trabajador': {
                'tipo_trabajador': (ct.type_worker_id.code if ct and ct.type_worker_id else '01'),
                'subtipo_trabajador': (ct.subtype_worker_id.code if ct and ct.subtype_worker_id else '00'),
                'alto_riesgo': 'true' if (ct and getattr(ct, 'high_risk_pension', False)) else 'false',
                'tipo_doc': self._ne_tipo_doc(e), 'numero_doc': e.identification_id or '',
                'ap1': self._ne_nombre(e, 'ap1'), 'ap2': self._ne_nombre(e, 'ap2'),
                'no1': self._ne_nombre(e, 'no1'), 'no2': self._ne_nombre(e, 'no2'),
                'lt_depto': t_depto, 'lt_muni': t_muni, 'lt_dir': t_dir,
                'salario_integral': 'true' if (ct and ct.integral_salary) else 'false',
                'tipo_contrato': self._ne_tipo_contrato(ct),
                'sueldo': _money(ct.wage if ct else 0.0),
                'codigo_trabajador': e.identification_id or '',
            },
            'pago': self._ne_pago(e),
            'fecha_pago': str(self.date_to or ''),
            'earn': earn, 'ded': ded, 'dias_trab': dias_trab,
            'dev_total': dev_total, 'ded_total': ded_total,
            'comprobante_total': round(dev_total - ded_total, 2),
        }

    @staticmethod
    def _ne_tipo_contrato(ct):
        if not ct:
            return '1'
        m = {'permanent': '1', 'indefinite': '1', 'fixed': '2', 'temporary': '2',
             'project': '3', 'apprentice': '4', 'internship': '5'}
        val = (getattr(ct, 'contract_type_id', False) and (ct.contract_type_id.code or '').lower()) or ''
        return m.get(val, '1')

    def _ne_pago(self, e):
        ba = e.bank_account_id
        return {
            'forma': '1',
            'metodo': '3' if ba else '10',
            'banco': (ba.bank_id.name if ba and ba.bank_id else '') or '',
            'tipo_cuenta': 'Ahorros',
            'cuenta': (ba.acc_number if ba else '') or '',
        }

    def _ne_totales(self, earn, ded):
        dev = sum(earn.values())
        de = sum(t for (_c, _cd, _n, t) in ded)
        return round(dev, 2), round(de, 2)

    # ------------------------------------------------------------------
    # CUNE (SHA-384) — Anexo Técnico Nómina Electrónica
    # ------------------------------------------------------------------
    def _ne_cune(self, datos, software_pin=''):
        cadena = '{num}{fec}{hora}{dev}{ded}{tot}{nit}{doc}{tipo}{pin}{amb}'.format(
            num=datos['secuencia']['numero'], fec=datos['fecha_gen'], hora=datos['hora_gen'],
            dev=_money(datos['dev_total']), ded=_money(datos['ded_total']),
            tot=_money(datos['comprobante_total']),
            nit=datos['empleador']['nit'], doc=datos['trabajador']['numero_doc'],
            tipo=datos['tipo_documento'], pin=software_pin, amb=datos['ambiente'])
        return sha384(cadena.encode()).hexdigest()

    def _ne_qr_url(self, cune):
        base = ('https://catalogo-vpfe-hab.dian.gov.co' if self.company_id.l10n_co_dian_test_environment
                else 'https://catalogo-vpfe.dian.gov.co')
        return '%s/document/searchqr?documentkey=%s' % (base, cune)

    # ------------------------------------------------------------------
    # Construcción del XML NominaIndividual (replica el patrón de oro)
    # ------------------------------------------------------------------
    def _ne_build_xml(self, datos, cune, op_mode=None, software_sc=''):
        from lxml import etree
        nsmap = {'xades': NS_XADES, 'xades141': NS_XADES141, 'ext': NS_EXT,
                 'ds': NS_DS, 'xs': NS_XSI, 'xsi': NS_XSI, None: NS}
        root = etree.Element('{%s}NominaIndividual' % NS, nsmap=nsmap)
        root.set('SchemaLocation', '')
        root.set('{%s}schemaLocation' % NS_XSI,
                 'dian:gov:co:facturaelectronica:NominaIndividual NominaIndividualElectronicaXSD.xsd')

        def S(parent, tag, _text=None, **attrs):
            el = etree.SubElement(parent, '{%s}%s' % (NS, tag))
            if _text is not None:
                el.text = str(_text)
            for k, v in attrs.items():
                el.set(k, str(v))
            return el

        p = datos['periodo']
        S(root, 'Periodo', FechaIngreso=p['ingreso'], FechaLiquidacionInicio=p['inicio'],
          FechaLiquidacionFin=p['fin'], TiempoLaborado=p['tiempo'], FechaGen=datos['fecha_gen'])
        sec = datos['secuencia']
        S(root, 'NumeroSecuenciaXML', CodigoTrabajador=datos['trabajador']['codigo_trabajador'],
          Prefijo=sec['prefijo'], Consecutivo=sec['consecutivo'], Numero=sec['numero'])
        S(root, 'LugarGeneracionXML', Pais='CO', DepartamentoEstado=datos['lugar']['depto'],
          MunicipioCiudad=datos['lugar']['muni'], Idioma='es')
        if op_mode is not None:
            S(root, 'ProveedorXML', NIT=datos['empleador']['nit'], DV=datos['empleador']['dv'],
              SoftwareID=op_mode.dian_software_id or '', SoftwareSC=software_sc or '')
        S(root, 'CodigoQR', _text=self._ne_qr_url(cune))
        S(root, 'InformacionGeneral',
          Version='V1.0: Documento Soporte de Pago de Nómina Electrónica',
          Ambiente=datos['ambiente'], TipoXML=datos['tipo_documento'], CUNE=cune,
          EncripCUNE='CUNE-SHA384', FechaGen=datos['fecha_gen'], HoraGen=datos['hora_gen'],
          PeriodoNomina=datos['periodo_nomina'], TipoMoneda='COP')
        em = datos['empleador']
        S(root, 'Empleador', RazonSocial=em['razon_social'], NIT=em['nit'], DV=em['dv'],
          Pais='CO', DepartamentoEstado=em['depto'], MunicipioCiudad=em['muni'], Direccion=em['dir'])
        tr = datos['trabajador']
        S(root, 'Trabajador', TipoTrabajador=tr['tipo_trabajador'], SubTipoTrabajador=tr['subtipo_trabajador'],
          AltoRiesgoPension=tr['alto_riesgo'], TipoDocumento=tr['tipo_doc'], NumeroDocumento=tr['numero_doc'],
          PrimerApellido=tr['ap1'], SegundoApellido=tr['ap2'], PrimerNombre=tr['no1'], OtrosNombres=tr['no2'],
          LugarTrabajoPais='CO', LugarTrabajoDepartamentoEstado=tr['lt_depto'],
          LugarTrabajoMunicipioCiudad=tr['lt_muni'], LugarTrabajoDireccion=tr['lt_dir'],
          SalarioIntegral=tr['salario_integral'], TipoContrato=tr['tipo_contrato'], Sueldo=tr['sueldo'])
        pg = datos['pago']
        S(root, 'Pago', Forma=pg['forma'], Metodo=pg['metodo'], Banco=pg['banco'],
          TipoCuenta=pg['tipo_cuenta'], NumeroCuenta=pg['cuenta'])
        fp = S(root, 'FechasPagos')
        S(fp, 'FechaPago', _text=datos['fecha_pago'])

        self._ne_build_devengados(S, root, datos)
        self._ne_build_deducciones(S, root, datos)

        S(root, 'DevengadosTotal', _text=_money(datos['dev_total']))
        S(root, 'DeduccionesTotal', _text=_money(datos['ded_total']))
        S(root, 'ComprobanteTotal', _text=_money(datos['comprobante_total']))
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8').decode()

    def _ne_build_devengados(self, S, root, datos):
        earn = dict(datos['earn'])
        dev = S(root, 'Devengados')
        # Básico (obligatorio)
        basico = earn.pop('basic', 0.0)
        S(dev, 'Basico', DiasTrabajados=datos['dias_trab'], SueldoTrabajado=_money(basico))
        # Transporte (auxilio + viáticos)
        aux = earn.pop('transports_assistance', 0.0)
        vs = earn.pop('transports_viatic', 0.0)
        vns = earn.pop('transports_non_salary_viatic', 0.0)
        if aux or vs or vns:
            attrs = {}
            if aux:
                attrs['AuxilioTransporte'] = _money(aux)
            if vs:
                attrs['ViaticoManuAlojS'] = _money(vs)
            if vns:
                attrs['ViaticoManuAlojNS'] = _money(vns)
            S(dev, 'Transporte', **attrs)
        # Vacaciones
        vac_c = earn.pop('vacation_common', 0.0)
        vac_comp = earn.pop('vacation_compensated', 0.0)
        if vac_c or vac_comp:
            v = S(dev, 'Vacaciones')
            if vac_c:
                S(v, 'VacacionesComunes', Cantidad=self._ne_cant('vacation_common'), Pago=_money(vac_c))
            if vac_comp:
                S(v, 'VacacionesCompensadas', Cantidad=self._ne_cant('vacation_compensated'), Pago=_money(vac_comp))
        # Primas
        prima_s = earn.pop('primas', 0.0)
        prima_ns = earn.pop('primas_non_salary', 0.0)
        if prima_s or prima_ns:
            attrs = {'Cantidad': '0'}
            if prima_s:
                attrs['Pago'] = _money(prima_s)
            if prima_ns:
                attrs['PagoNS'] = _money(prima_ns)
            S(dev, 'Primas', **attrs)
        # Cesantías
        ces = earn.pop('layoffs', 0.0)
        ces_int = earn.pop('layoffs_interest', 0.0)
        if ces or ces_int:
            S(dev, 'Cesantias', Pago=_money(ces), Porcentaje='0.00', PagoIntereses=_money(ces_int))
        # Incapacidades
        inc = {'incapacities_common': ('1', earn.pop('incapacities_common', 0.0)),
               'incapacities_professional': ('2', earn.pop('incapacities_professional', 0.0)),
               'incapacities_working': ('3', earn.pop('incapacities_working', 0.0))}
        if any(v for _t, v in inc.values()):
            ic = S(dev, 'Incapacidades')
            for _k, (tipo, val) in inc.items():
                if val:
                    S(ic, 'Incapacidad', Cantidad='0', Tipo=tipo, Pago=_money(val))
        # Licencias
        lic_mp = earn.pop('licensings_maternity_or_paternity_leaves', 0.0)
        lic_r = earn.pop('licensings_permit_or_paid_licenses', 0.0)
        lic_nr = earn.pop('licensings_suspension_or_unpaid_leaves', 0.0)
        if lic_mp or lic_r or lic_nr:
            lc = S(dev, 'Licencias')
            if lic_mp:
                S(lc, 'LicenciaMP', Cantidad='0', Pago=_money(lic_mp))
            if lic_r:
                S(lc, 'LicenciaR', Cantidad='0', Pago=_money(lic_r))
            if lic_nr:
                S(lc, 'LicenciaNR', Cantidad='0')
        # Bonificaciones
        bon_s = earn.pop('bonuses', 0.0)
        bon_ns = earn.pop('bonuses_non_salary', 0.0)
        if bon_s or bon_ns:
            bs = S(dev, 'Bonificaciones')
            attrs = {}
            if bon_s:
                attrs['BonificacionS'] = _money(bon_s)
            if bon_ns:
                attrs['BonificacionNS'] = _money(bon_ns)
            S(bs, 'Bonificacion', **attrs)
        # Auxilios
        aux_s = earn.pop('assistances', 0.0)
        aux_ns = earn.pop('assistances_non_salary', 0.0)
        if aux_s or aux_ns:
            au = S(dev, 'Auxilios')
            attrs = {}
            if aux_s:
                attrs['AuxilioS'] = _money(aux_s)
            if aux_ns:
                attrs['AuxilioNS'] = _money(aux_ns)
            S(au, 'Auxilio', **attrs)
        # Comisiones
        com = earn.pop('commissions', 0.0)
        if com:
            cm = S(dev, 'Comisiones')
            S(cm, 'Comision', _text=_money(com))
        # Compensaciones
        comp = earn.pop('compensations_ordinary', 0.0) + earn.pop('compensations_extraordinary', 0.0)
        if comp:
            cp = S(dev, 'Compensaciones')
            S(cp, 'Compensacion', Ordinaria=_money(comp))
        # Bono retiro
        bono_ret = earn.pop('company_withdrawal_bonus', 0.0)
        if bono_ret:
            br = S(dev, 'BonoEPCTVs')
            S(br, 'BonoEPCTV', PagoS=_money(bono_ret))
        # Otros conceptos (todo lo restante)
        otros = sum(earn.values())
        if otros:
            oc = S(dev, 'OtrosConceptos')
            S(oc, 'OtroConcepto', ConceptoS='Otros devengados', DescripcionConceptoS='Otros', PagoS=_money(otros))

    def _ne_cant(self, cat):
        """Cantidad (días) del concepto, tomada de la earn.line con esa categoría."""
        self.ensure_one()
        q = sum(abs(e.quantity or 0.0) for e in self.earn_ids if e.category == cat)
        return str(int(round(q))) if q else '1'

    def _ne_build_deducciones(self, S, root, datos):
        ded = S(root, 'Deducciones')
        salud = pension = fsp = 0.0
        libranzas = []
        retencion = cooperativa = reintegro = otras = 0.0
        for cat, code, name, total in datos['ded']:
            if cat == 'health' or code in ('salud',):
                salud += total
            elif cat == 'pension' or code in ('pens', 'pension'):
                pension += total
            elif cat in ('fsp', 'fund', 'solidarity') or code in ('fsp',):
                fsp += total
            elif cat in ('withholding', 'rtf') or code in ('rtf', 'retefuente'):
                retencion += total
            elif cat in ('libranzas', 'loan') or 'libranza' in code:
                libranzas.append((name, total))
            elif 'cooper' in cat or 'cooper' in code or 'fondo' in code:
                cooperativa += total
            elif cat == 'refund' or 'reintegr' in code:
                reintegro += total
            else:
                otras += total
        if salud:
            S(ded, 'Salud', Porcentaje='4.00', Deduccion=_money(salud))
        if pension:
            S(ded, 'FondoPension', Porcentaje='4.00', Deduccion=_money(pension))
        if fsp:
            S(ded, 'FondoSP', Porcentaje='1.00', DeduccionSP=_money(fsp))
        if libranzas:
            lb = S(ded, 'Libranzas')
            for name, total in libranzas:
                S(lb, 'Libranza', Descripcion=(name or 'Libranza')[:100], Deduccion=_money(total))
        if retencion:
            S(ded, 'RetencionFuente', _text=_money(retencion))
        if cooperativa:
            S(ded, 'Cooperativa', _text=_money(cooperativa))
        if reintegro:
            S(ded, 'Reintegro', _text=_money(reintegro))
        if otras:
            od = S(ded, 'OtrasDeducciones')
            S(od, 'OtraDeduccion', Deduccion=_money(otras))
