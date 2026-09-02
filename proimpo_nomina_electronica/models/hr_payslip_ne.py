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
NS_XS = "http://www.w3.org/2001/XMLSchema"  # URI correcto de 'xs' (distinto de xsi)
NS_AJUSTE = "dian:gov:co:facturaelectronica:NominaIndividualDeAjuste"
VERSION_NOMINA = 'V1.0: Documento Soporte de Pago de Nómina Electrónica'
VERSION_AJUSTE = 'V1.0: Nota de Ajuste de Documento Soporte de Pago de Nómina Electrónica'

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
        ('replaced', 'Reemplazado (nota de ajuste)'), ('deleted', 'Eliminado (nota de ajuste)'),
    ], string="Estado NE", default='draft', copy=False)
    # v4.3.0 - Nota de ajuste (tipo 103)
    ne_numero = fields.Char(string="Número NE (DIAN)", copy=False, readonly=True,
                            help="Numero del documento tal como fue enviado a la DIAN (prefijo+consecutivo).")
    ne_fecha_gen = fields.Char(string="FechaGen NE", copy=False, readonly=True)
    ne_reemplaza_id = fields.Many2one('hr.payslip', string="Reemplaza a (nota de ajuste)", copy=False,
                                      readonly=True, help="Recibo aceptado por la DIAN que esta nota corrige.")
    ne_tipo_nota = fields.Selection([('1', 'Reemplazar'), ('2', 'Eliminar')], string="Tipo de nota",
                                    compute='_compute_ne_tipo_nota', store=False)
    ne_ajuste_ids = fields.One2many('hr.payslip', 'ne_reemplaza_id', string="Notas de reemplazo")

    @api.depends('ne_reemplaza_id', 'credit_note', 'origin_payslip_id')
    def _compute_ne_tipo_nota(self):
        for rec in self:
            if rec.ne_reemplaza_id:
                rec.ne_tipo_nota = '1'
            elif getattr(rec, 'credit_note', False) and getattr(rec, 'origin_payslip_id', False):
                rec.ne_tipo_nota = '2'
            else:
                rec.ne_tipo_nota = False

    def _ne_predecesor(self):
        """Recibo original al que esta nota de ajuste hace referencia (o vacio)."""
        self.ensure_one()
        if self.ne_reemplaza_id:
            return self.ne_reemplaza_id
        if getattr(self, 'credit_note', False) and getattr(self, 'origin_payslip_id', False):
            return self.origin_payslip_id
        return self.browse()

    def _ne_datos_predecesor(self):
        """(NumeroPred, CUNEPred, FechaGenPred) del recibo original aceptado."""
        from odoo.exceptions import UserError
        pred = self._ne_predecesor()
        if not pred:
            raise UserError(_("Esta nota de ajuste no tiene recibo original asociado."))
        if pred.ne_state not in ('accepted', 'replaced', 'deleted') or not pred.ne_cune:
            raise UserError(_("El recibo original %s no esta ACEPTADO por la DIAN; "
                              "solo se pueden ajustar documentos aceptados.") % (pred.number or pred.id))
        numero = pred.ne_numero
        fecha = pred.ne_fecha_gen
        if (not numero or not fecha) and pred.ne_xml:
            # Documentos aceptados antes de v4.3.0: leer del XML enviado
            from lxml import etree
            try:
                r = etree.fromstring(pred.ne_xml.encode('utf-8'))
                sec = r.find('{%s}NumeroSecuenciaXML' % NS)
                ig = r.find('{%s}InformacionGeneral' % NS)
                numero = numero or (sec.get('Numero') if sec is not None else '')
                fecha = fecha or (ig.get('FechaGen') if ig is not None else '')
            except Exception:
                pass
        if not numero or not fecha:
            raise UserError(_("No se pudo determinar el numero o la fecha de generacion del recibo original."))
        return numero, pred.ne_cune, fecha

    # ------------------------------------------------------------------
    # Conceptos desde las LÍNEAS de reglas salariales (line_ids)
    # PROIMPO calcula devengados/deducciones con reglas, no con earn.line.
    # Se excluyen categorías computacionales y de aportes/provisiones.
    # ------------------------------------------------------------------
    def _ne_conceptos(self):
        """Devuelve (dev, ded, qty):
          dev = {bucket: monto}   ded = {bucket: monto, 'libranzas':[(nom,monto)]}
          qty = {bucket: cantidad_dias}"""
        self.ensure_one()
        dev = {}
        ded = {'libranzas': [], 'otras': []}
        otros = []      # [(descripcion, monto)] -> OtrosConceptos/OtroConcepto
        qty = {}
        for line in self.line_ids:
            total = round(line.total or 0.0, 2)
            if not total:
                continue
            cat = (line.category_id.name or '').lower()
            catc = (line.category_id.code or '').lower()
            code = (line.salary_rule_id.code or '').lower()
            name = (line.name or '').lower()
            # Excluir: bases de cálculo, bruto, neto, aportes patronales, provisiones
            if ('aporte' in cat or 'provis' in cat or 'base' in cat
                    or cat.strip() in ('bruto', 'neto', 'gross', 'net', 'total')
                    or catc in ('aporte', 'prov', 'provision', 'base', 'bruto', 'neto', 'ibc')):
                continue
            es_ded = ('deduc' in cat) or (catc in ('ded', 'deduction'))
            if es_ded:
                b = self._ne_ded_bucket(code, name)
                amt = abs(total)
                if b == 'libranzas':
                    ded['libranzas'].append((line.name or 'Libranza', amt))
                elif b == 'otras':
                    ded['otras'].append(amt)
                else:
                    ded[b] = ded.get(b, 0.0) + amt
            else:
                b = self._ne_dev_bucket(code, name)
                if b == 'horas':
                    # Horas extras/recargos: el detalle sale de earn_ids (HED/HEN/HRN...).
                    # Si no hay detalle, se reporta como OtroConcepto con su descripcion.
                    if not self._ne_tiene_detalle_horas():
                        otros.append((line.name or 'Horas extras', total))
                    continue
                if b == 'otros':
                    otros.append((line.name or 'Otro concepto', total))
                    continue
                # v4.2.5: un devengado negativo (p.ej. "Mayor valor pagado comision") se
                # netea contra su mismo bucket; si el bucket queda negativo, pasa a
                # OtraDeduccion (ver abajo).
                dev[b] = dev.get(b, 0.0) + total
                q = abs(line.quantity or 0.0)
                if q and q != 1.0:
                    qty[b] = qty.get(b, 0.0) + q
        # Otros conceptos: agrupar por descripcion; negativos -> OtraDeduccion
        agg = {}
        for n, a in otros:
            agg[n] = agg.get(n, 0.0) + a
        dev['otros'] = [(n, round(a, 2)) for n, a in agg.items() if round(a, 2) > 0]
        for n, a in agg.items():
            if round(a, 2) < 0:
                ded['otras'].append(abs(round(a, 2)))
        for b in list(dev.keys()):
            if b != 'otros' and round(dev[b], 2) < 0:
                ded['otras'].append(abs(round(dev[b], 2)))
                dev[b] = 0.0
        return dev, ded, qty

    # Categorias del motor (earn.line) -> elemento DIAN y porcentaje de recargo
    _NE_HORAS = {
        'daily_overtime':                         ('HEDs',   'HED',   '25.00'),
        'overtime_night_hours':                   ('HENs',   'HEN',   '75.00'),
        'hours_night_surcharge':                  ('HRNs',   'HRN',   '35.00'),
        'sunday_holiday_daily_overtime':          ('HEDDFs', 'HEDDF', '100.00'),
        'daily_surcharge_hours_sundays_holidays': ('HRDDFs', 'HRDDF', '75.00'),
        'sunday_night_overtime_holidays':         ('HENDFs', 'HENDF', '150.00'),
        'sunday_holidays_night_surcharge_hours':  ('HRNDFs', 'HRNDF', '110.00'),
    }

    def _ne_tiene_detalle_horas(self):
        self.ensure_one()
        return any(e.category in self._NE_HORAS and e.total for e in getattr(self, 'earn_ids', []))

    def _ne_detalle_horas(self):
        """[(parent, child, {HoraInicio, HoraFin, Cantidad, Porcentaje, Pago})] desde earn_ids,
        en el orden del XSD."""
        self.ensure_one()
        from datetime import datetime, timedelta
        out = {}
        for e in getattr(self, 'earn_ids', []):
            m = self._NE_HORAS.get(e.category)
            if not m or not e.total:
                continue
            attrs = {}
            if e.date_start:
                ini = datetime(e.date_start.year, e.date_start.month, e.date_start.day) + timedelta(hours=e.time_start or 0.0)
                fin_d = e.date_end or e.date_start
                fin = datetime(fin_d.year, fin_d.month, fin_d.day) + timedelta(hours=e.time_end or 0.0)
                if fin <= ini:
                    fin = ini + timedelta(hours=abs(e.quantity or 1.0))
                attrs['HoraInicio'] = ini.strftime('%Y-%m-%dT%H:%M:%S')
                attrs['HoraFin'] = fin.strftime('%Y-%m-%dT%H:%M:%S')
            attrs['Cantidad'] = ('%.2f' % abs(e.quantity or 1.0)).rstrip('0').rstrip('.')
            attrs['Porcentaje'] = m[2]
            attrs['Pago'] = _money(abs(e.total))
            out.setdefault(e.category, []).append(attrs)
        res = []
        for cat, m in self._NE_HORAS.items():
            for attrs in out.get(cat, []):
                res.append((m[0], m[1], attrs))
        return res

    @staticmethod
    def _ne_dev_bucket(code, name):
        n = name
        if 'transporte' in n or code in ('trans', 'auxt', 'transp'):
            if 'viátic' in n or 'viatic' in n:
                return 'transporte_vns' if ('no salarial' in n or ' ns' in n) else 'transporte_vs'
            return 'transporte_aux'
        if 'básico' in n or 'basico' in n or code in ('basic', 'sueldo', 'salariobasico'):
            return 'basico'
        if 'hora' in n or 'recargo' in n or 'extra' in n:
            return 'horas'
        if 'vacacion' in n:
            return 'vacaciones'
        if 'cesant' in n:
            return 'cesantias_int' if 'interes' in n or 'interés' in n else 'cesantias'
        if 'prima' in n:
            return 'primas_ns' if 'no salarial' in n else 'primas_s'
        if 'bonif' in n:
            return 'bonif_ns' if 'no salarial' in n else 'bonif_s'
        if 'comis' in n:
            return 'comisiones'
        if 'auxilio' in n:
            return 'aux_ns' if 'no salarial' in n else 'aux_s'
        return 'otros'

    @staticmethod
    def _ne_ded_bucket(code, name):
        n = name
        if 'salud' in n:
            return 'salud'
        if 'solidaridad' in n or 'fsp' in code or 'fondo de solidaridad' in n:
            return 'fsp'
        # v4.2.2: pension voluntaria y AFC van en sus propios elementos (no en FondoPension)
        if 'voluntar' in n or code in ('pensvol', 'pens_vol', 'pvol'):
            return 'pension_voluntaria'
        if 'afc' in n.split() or code in ('afc',) or 'cuenta afc' in n or 'ahorro para el fomento' in n:
            return 'afc'
        if 'pensión' in n or 'pension' in n or code in ('pens',):
            return 'pension'
        if 'retención' in n or 'retencion' in n or 'fuente' in n or code in ('rtf', 'retefuente'):
            return 'retencion'
        if 'libranza' in n:
            return 'libranzas'
        if 'cooper' in n or 'fondo de emplead' in n or 'fondo emplead' in n:
            return 'cooperativa'
        return 'otras'

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

        dev, ded, qty = self._ne_conceptos()
        dev_total, ded_total = self._ne_totales(dev, ded)

        # Prefijo + consecutivo del número del documento
        tipo_nota = self.ne_tipo_nota
        nota = None
        if tipo_nota:
            # v4.3.0: nota de ajuste (103) con secuencia propia NA + consecutivo
            if not self.ne_numero:
                seq = self.env['ir.sequence'].sudo().next_by_code('proimpo.ne.ajuste') or str(self.id)
                self.ne_numero = 'NA' + ''.join(c for c in seq if c.isdigit())
            prefijo, consecutivo = 'NA', self.ne_numero[2:]
            numero_full = self.ne_numero
            pn, pc, pf = self._ne_datos_predecesor()
            nota = {'tipo': tipo_nota, 'pred_numero': pn, 'pred_cune': pc, 'pred_fecha': pf}
        else:
            numero = (self.number or '').replace(' ', '').replace('-', '')
            prefijo = ''.join(c for c in numero if not c.isdigit())[:4] or 'NE'
            consecutivo = ''.join(c for c in numero if c.isdigit()) or str(self.id)
            numero_full = prefijo + consecutivo
        if nota and nota['tipo'] == '2':
            # Eliminar: sin devengados/deducciones; el CUNE se calcula con 0.00
            dev, ded, qty = {}, {'libranzas': [], 'otras': []}, {}
            dev_total, ded_total = 0.0, 0.0

        dias_trab = self._ne_dias_trabajados()
        tiempo_lab = dias_trab
        if ct and ct.date_start and self.date_to:
            tiempo_lab = max(0, (self.date_to - ct.date_start).days)

        return {
            'tipo_documento': '103' if nota else '102',
            'nota': nota,
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
            'dev': dev, 'ded': ded, 'qty': qty, 'dias_trab': dias_trab,
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

    def _ne_totales(self, dev, ded):
        dev_t = sum(v for k, v in dev.items() if k != 'otros')
        dev_t += sum(a for _n, a in dev.get('otros', []))
        dev_t += sum(float(h[2]['Pago']) for h in self._ne_detalle_horas())
        ded_t = sum(v for k, v in ded.items() if k not in ('libranzas', 'otras'))
        ded_t += sum(a for _n, a in ded.get('libranzas', []))
        ded_t += sum(ded.get('otras', []))
        return round(dev_t, 2), round(ded_t, 2)

    # ------------------------------------------------------------------
    # CUNE (SHA-384) — Anexo Técnico Nómina Electrónica
    # ------------------------------------------------------------------
    def _ne_cune(self, datos, software_pin=''):
        # Anexo tecnico 8.1.1.4: para la nota de ajuste ELIMINAR, ValDev/ValDed/ValTol = 0.00
        # y DocEmp = 0 (no la cedula del trabajador). v4.3.1 (regla NIAE238).
        nota = datos.get('nota')
        eliminar = bool(nota and nota.get('tipo') == '2')
        cadena = '{num}{fec}{hora}{dev}{ded}{tot}{nit}{doc}{tipo}{pin}{amb}'.format(
            num=datos['secuencia']['numero'], fec=datos['fecha_gen'], hora=datos['hora_gen'],
            dev='0.00' if eliminar else _money(datos['dev_total']),
            ded='0.00' if eliminar else _money(datos['ded_total']),
            tot='0.00' if eliminar else _money(datos['comprobante_total']),
            nit=datos['empleador']['nit'],
            doc='0' if eliminar else datos['trabajador']['numero_doc'],
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
        # v4.2.0: la raiz se construye desde texto para replicar BYTE A BYTE la raiz de las
        # nominas ACEPTADAS por la DIAN (GOMEZ/AGUILAR): orden de namespaces
        # default, xs, ds, ext, xades, xades141, xsi y atributo xsi:schemaLocation.
        # 'xs' y 'xsi' AMBOS = XMLSchema-instance (lo exige NIE901). Con nsmap de lxml el
        # orden cambia y el atributo sale como xs:schemaLocation; un validador que remapee
        # prefijos duplicados alteraria el digest del documento -> ZE02.
        root = etree.fromstring(
            '<NominaIndividual xmlns="%s" xmlns:xs="%s" xmlns:ds="%s" xmlns:ext="%s" '
            'xmlns:xades="%s" xmlns:xades141="%s" xmlns:xsi="%s" SchemaLocation="" '
            'xsi:schemaLocation="dian:gov:co:facturaelectronica:NominaIndividual '
            'NominaIndividualElectronicaXSD.xsd"/>'
            % (NS, NS_XSI, NS_DS, NS_EXT, NS_XADES, NS_XADES141, NS_XSI))

        def S(parent, tag, _text=None, **attrs):
            el = etree.SubElement(parent, '{%s}%s' % (NS, tag))
            if _text is not None:
                el.text = str(_text)
            for k, v in attrs.items():
                el.set(k, str(v))
            return el

        # v4.2.0: elementos opcionales presentes en las nóminas ACEPTADAS (GOMEZ/AGUILAR):
        # Novedad, RazonSocial en ProveedorXML, TRM, Notas, CodigoTrabajador y Redondeo.
        S(root, 'Novedad', _text='false', CUNENov=cune)
        self._ne_build_cuerpo(S, root, datos, cune, op_mode, software_sc)
        return etree.tostring(root, encoding='UTF-8').decode()

    def _ne_build_cuerpo(self, S, root, datos, cune, op_mode, software_sc):
        """Periodo ... ComprobanteTotal (comun a NominaIndividual y a Reemplazar)."""
        p = datos['periodo']
        S(root, 'Periodo', FechaIngreso=p['ingreso'], FechaLiquidacionInicio=p['inicio'],
          FechaLiquidacionFin=p['fin'], TiempoLaborado=p['tiempo'], FechaGen=datos['fecha_gen'])
        sec = datos['secuencia']
        S(root, 'NumeroSecuenciaXML', CodigoTrabajador=datos['trabajador']['codigo_trabajador'],
          Prefijo=sec['prefijo'], Consecutivo=sec['consecutivo'], Numero=sec['numero'])
        S(root, 'LugarGeneracionXML', Pais='CO', DepartamentoEstado=datos['lugar']['depto'],
          MunicipioCiudad=datos['lugar']['muni'], Idioma='es')
        if op_mode is not None:
            S(root, 'ProveedorXML', RazonSocial=datos['empleador']['razon_social'],
              NIT=datos['empleador']['nit'], DV=datos['empleador']['dv'],
              SoftwareID=op_mode.dian_software_id or '', SoftwareSC=software_sc or '')
        S(root, 'CodigoQR', _text=self._ne_qr_url(cune))
        S(root, 'InformacionGeneral',
          Version=(VERSION_AJUSTE if datos.get('nota') else VERSION_NOMINA),
          Ambiente=datos['ambiente'], TipoXML=datos['tipo_documento'], CUNE=cune,
          EncripCUNE='CUNE-SHA384', FechaGen=datos['fecha_gen'], HoraGen=datos['hora_gen'],
          PeriodoNomina=datos['periodo_nomina'], TipoMoneda='COP', TRM='0')
        if datos.get('nota'):
            S(root, 'Notas', _text='REEMPLAZA NOMINA %s' % datos['nota']['pred_numero'])
        else:
            S(root, 'Notas', _text='NOMINA %s %s A %s' % (sec['numero'], p['inicio'], p['fin']))
        em = datos['empleador']
        S(root, 'Empleador', RazonSocial=em['razon_social'], NIT=em['nit'], DV=em['dv'],
          Pais='CO', DepartamentoEstado=em['depto'], MunicipioCiudad=em['muni'], Direccion=em['dir'])
        tr = datos['trabajador']
        # v4.2.3: segun el XSD oficial, SegundoApellido es OBLIGATORIO (use="required",
        # puede ir vacio) y OtrosNombres es opcional; la DIAN (NIE049) rechaza
        # OtrosNombres presente pero vacio -> solo se emite cuando tiene valor.
        tr_attrs = {'TipoTrabajador': tr['tipo_trabajador'], 'SubTipoTrabajador': tr['subtipo_trabajador'],
                    'AltoRiesgoPension': tr['alto_riesgo'], 'TipoDocumento': tr['tipo_doc'],
                    'NumeroDocumento': tr['numero_doc'], 'PrimerApellido': tr['ap1'],
                    'SegundoApellido': (tr['ap2'] or '').strip(), 'PrimerNombre': tr['no1']}
        if (tr['no2'] or '').strip():
            tr_attrs['OtrosNombres'] = tr['no2'].strip()
        S(root, 'Trabajador', **tr_attrs,
          LugarTrabajoPais='CO', LugarTrabajoDepartamentoEstado=tr['lt_depto'],
          LugarTrabajoMunicipioCiudad=tr['lt_muni'], LugarTrabajoDireccion=tr['lt_dir'],
          SalarioIntegral=tr['salario_integral'], TipoContrato=tr['tipo_contrato'], Sueldo=tr['sueldo'],
          CodigoTrabajador=tr['codigo_trabajador'])
        pg = datos['pago']
        pago_attrs = {'Forma': pg['forma'], 'Metodo': pg['metodo']}
        if pg['banco']:
            pago_attrs['Banco'] = pg['banco']
        if pg['cuenta']:
            pago_attrs['TipoCuenta'] = pg['tipo_cuenta']
            pago_attrs['NumeroCuenta'] = pg['cuenta']
        S(root, 'Pago', **pago_attrs)
        fp = S(root, 'FechasPagos')
        S(fp, 'FechaPago', _text=datos['fecha_pago'])

        self._ne_build_devengados(S, root, datos)
        self._ne_build_deducciones(S, root, datos)

        S(root, 'Redondeo', _text='0.00')
        S(root, 'DevengadosTotal', _text=_money(datos['dev_total']))
        S(root, 'DeduccionesTotal', _text=_money(datos['ded_total']))
        S(root, 'ComprobanteTotal', _text=_money(datos['comprobante_total']))

    # ------------------------------------------------------------------
    # v4.3.0 - XML NominaIndividualDeAjuste (tipo 103): Reemplazar / Eliminar
    # ------------------------------------------------------------------
    def _ne_build_xml_ajuste(self, datos, cune, op_mode=None, software_sc=''):
        from lxml import etree
        nota = datos['nota']
        # Misma raiz (orden de namespaces) que la nomina aceptada, con el XSD de ajuste
        root = etree.fromstring(
            '<NominaIndividualDeAjuste xmlns="%s" xmlns:xs="%s" xmlns:ds="%s" xmlns:ext="%s" '
            'xmlns:xades="%s" xmlns:xades141="%s" xmlns:xsi="%s" SchemaLocation="" '
            'xsi:schemaLocation="dian:gov:co:facturaelectronica:NominaIndividualDeAjuste '
            'NominaIndividualDeAjusteElectronicaXSD.xsd"/>'
            % (NS_AJUSTE, NS_XSI, NS_DS, NS_EXT, NS_XADES, NS_XADES141, NS_XSI))

        def S(parent, tag, _text=None, **attrs):
            el = etree.SubElement(parent, '{%s}%s' % (NS_AJUSTE, tag))
            if _text is not None:
                el.text = str(_text)
            for k, v in attrs.items():
                el.set(k, str(v))
            return el

        S(root, 'TipoNota', _text=nota['tipo'])
        pred = dict(NumeroPred=nota['pred_numero'], CUNEPred=nota['pred_cune'], FechaGenPred=nota['pred_fecha'])
        if nota['tipo'] == '1':
            r = S(root, 'Reemplazar')
            S(r, 'ReemplazandoPredecesor', **pred)
            self._ne_build_cuerpo(S, r, datos, cune, op_mode, software_sc)
        else:
            e = S(root, 'Eliminar')
            S(e, 'EliminandoPredecesor', **pred)
            sec = datos['secuencia']
            S(e, 'NumeroSecuenciaXML', Prefijo=sec['prefijo'], Consecutivo=sec['consecutivo'], Numero=sec['numero'])
            S(e, 'LugarGeneracionXML', Pais='CO', DepartamentoEstado=datos['lugar']['depto'],
              MunicipioCiudad=datos['lugar']['muni'], Idioma='es')
            if op_mode is not None:
                S(e, 'ProveedorXML', RazonSocial=datos['empleador']['razon_social'],
                  NIT=datos['empleador']['nit'], DV=datos['empleador']['dv'],
                  SoftwareID=op_mode.dian_software_id or '', SoftwareSC=software_sc or '')
            S(e, 'CodigoQR', _text=self._ne_qr_url(cune))
            S(e, 'InformacionGeneral', Version=VERSION_AJUSTE,
              Ambiente=datos['ambiente'], TipoXML=datos['tipo_documento'], CUNE=cune,
              EncripCUNE='CUNE-SHA384', FechaGen=datos['fecha_gen'], HoraGen=datos['hora_gen'])
            S(e, 'Notas', _text='ELIMINA NOMINA %s' % nota['pred_numero'])
            em = datos['empleador']
            S(e, 'Empleador', RazonSocial=em['razon_social'], NIT=em['nit'], DV=em['dv'],
              Pais='CO', DepartamentoEstado=em['depto'], MunicipioCiudad=em['muni'], Direccion=em['dir'])
        return etree.tostring(root, encoding='UTF-8').decode()

    def _ne_build_devengados(self, S, root, datos):
        dev = datos['dev']
        qty = datos.get('qty', {})
        d = S(root, 'Devengados')

        def g(k):
            v = dev.get(k, 0.0)
            return v if isinstance(v, (int, float)) else 0.0

        def cant(k, default='1'):
            q = qty.get(k)
            return str(int(round(q))) if q else default

        # Básico (obligatorio)
        S(d, 'Basico', DiasTrabajados=datos['dias_trab'], SueldoTrabajado=_money(g('basico')))
        # Transporte (auxilio + viáticos)
        if g('transporte_aux') or g('transporte_vs') or g('transporte_vns'):
            attrs = {}
            if g('transporte_aux'):
                attrs['AuxilioTransporte'] = _money(g('transporte_aux'))
            if g('transporte_vs'):
                attrs['ViaticoManuAlojS'] = _money(g('transporte_vs'))
            if g('transporte_vns'):
                attrs['ViaticoManuAlojNS'] = _money(g('transporte_vns'))
            S(d, 'Transporte', **attrs)
        # Horas extras y recargos (HEDs, HENs, HRNs, HEDDFs, HRDDFs, HENDFs, HRNDFs)
        parents = {}
        for parent, child, attrs in self._ne_detalle_horas():
            if parent not in parents:
                parents[parent] = S(d, parent)
            S(parents[parent], child, **attrs)
        # Vacaciones
        if g('vacaciones'):
            v = S(d, 'Vacaciones')
            S(v, 'VacacionesComunes', Cantidad=cant('vacaciones'), Pago=_money(g('vacaciones')))
        # Primas
        if g('primas_s') or g('primas_ns'):
            attrs = {'Cantidad': '0'}
            if g('primas_s'):
                attrs['Pago'] = _money(g('primas_s'))
            if g('primas_ns'):
                attrs['PagoNS'] = _money(g('primas_ns'))
            S(d, 'Primas', **attrs)
        # Cesantías
        if g('cesantias') or g('cesantias_int'):
            S(d, 'Cesantias', Pago=_money(g('cesantias')), Porcentaje='0.00',
              PagoIntereses=_money(g('cesantias_int')))
        # Bonificaciones
        if g('bonif_s') or g('bonif_ns'):
            bs = S(d, 'Bonificaciones')
            attrs = {}
            if g('bonif_s'):
                attrs['BonificacionS'] = _money(g('bonif_s'))
            if g('bonif_ns'):
                attrs['BonificacionNS'] = _money(g('bonif_ns'))
            S(bs, 'Bonificacion', **attrs)
        # Auxilios
        if g('aux_s') or g('aux_ns'):
            au = S(d, 'Auxilios')
            attrs = {}
            if g('aux_s'):
                attrs['AuxilioS'] = _money(g('aux_s'))
            if g('aux_ns'):
                attrs['AuxilioNS'] = _money(g('aux_ns'))
            S(au, 'Auxilio', **attrs)
        # Otros conceptos (XSD: DescripcionConcepto obligatorio + ConceptoS/ConceptoNS)
        otros = dev.get('otros') or []
        if otros:
            oc = S(d, 'OtrosConceptos')
            for nombre, monto in otros:
                S(oc, 'OtroConcepto', DescripcionConcepto=(nombre or 'Otro concepto')[:100],
                  ConceptoS=_money(monto))
        # Comisiones (XSD: despues de OtrosConceptos)
        if g('comisiones'):
            cm = S(d, 'Comisiones')
            S(cm, 'Comision', _text=_money(g('comisiones')))

    def _ne_build_deducciones(self, S, root, datos):
        ded = datos['ded']
        d = S(root, 'Deducciones')
        # Salud y FondoPension son OBLIGATORIOS en el XSD (1-1). Un pensionado (sin aporte a
        # pension) o un caso sin aporte a salud se reporta con Porcentaje y Deduccion en 0.00
        # (NIE164/NIE166: "el porcentaje/valor que corresponda"). v4.3.2
        S(d, 'Salud', Porcentaje='4.00' if ded.get('salud') else '0.00', Deduccion=_money(ded.get('salud', 0.0)))
        S(d, 'FondoPension', Porcentaje='4.00' if ded.get('pension') else '0.00',
          Deduccion=_money(ded.get('pension', 0.0)))
        if ded.get('fsp'):
            S(d, 'FondoSP', Porcentaje='1.00', DeduccionSP=_money(ded['fsp']))
        if ded.get('libranzas'):
            lb = S(d, 'Libranzas')
            for name, total in ded['libranzas']:
                S(lb, 'Libranza', Descripcion=(name or 'Libranza')[:100], Deduccion=_money(total))
        # Orden EXACTO del XSD: ... Libranzas, OtrasDeducciones, PensionVoluntaria,
        # RetencionFuente, AFC, Cooperativa, Reintegro
        if ded.get('otras'):
            od = S(d, 'OtrasDeducciones')
            for monto in ded['otras']:
                S(od, 'OtraDeduccion', _text=_money(monto))
        if ded.get('pension_voluntaria'):
            S(d, 'PensionVoluntaria', _text=_money(ded['pension_voluntaria']))
        if ded.get('retencion'):
            S(d, 'RetencionFuente', _text=_money(ded['retencion']))
        if ded.get('afc'):
            S(d, 'AFC', _text=_money(ded['afc']))
        if ded.get('cooperativa'):
            S(d, 'Cooperativa', _text=_money(ded['cooperativa']))
        if ded.get('reintegro'):
            S(d, 'Reintegro', _text=_money(ded['reintegro']))
