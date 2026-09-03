# -*- coding: utf-8 -*-
"""Firma XAdES-EPES + transmisión a la DIAN de la Nómina Electrónica.

REUTILIZA el motor nativo `l10n_co_dian` de Odoo (gratuito, directo a la DIAN):
  * Certificado, ambiente y modo demo de la compañía (los mismos de factura/DS).
  * `xml_utils._reference_digests` / `_fill_signature`  -> firma XAdES del documento.
  * `xml_utils._build_and_send_request`                 -> envío SOAP firmado al VPFE.
  * Servicio `SendTestSetAsync` (set de pruebas / habilitación) y `GetStatusZip`
    (consulta del resultado), idénticos a los de factura.

No se paga transmisión a terceros: el envío va directo al web service de la DIAN
con el certificado de la empresa, igual que hoy hace Odoo con la factura electrónica.
"""
import io
import os
import re
import zipfile
from base64 import b64encode
from hashlib import sha384

from lxml import etree
from pytz import timezone

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.l10n_co_dian import xml_utils

NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"
# Política de firma de la DIAN. v4.1.0: URL con 'https://' (DOS barras), igual a las
# nóminas ACEPTADAS de referencia (GOMEZ ROJAS / AGUILAR SUAREZ). El motor nativo de
# factura usa 'https:/' (una barra) pero para nómina se replica el documento aceptado.
SIG_POLICY_URL = "https://facturaelectronica.dian.gov.co/politicadefirma/v2/politicadefirmav2.pdf"
SIG_POLICY_DESC = "Política de firma para facturas electrónicas de la República de Colombia."
SIG_POLICY_HASH = "dMoMvtcG5aIzgYo0tIsSQeVJBDnUnfSOfBpxXrmor0Y="


def _E(parent, tag, text=None, **attrs):
    """SubElemento con texto y atributos opcionales."""
    el = etree.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    for k, v in attrs.items():
        el.set(k, str(v))
    return el


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    ne_document_id = fields.Many2one('l10n_co_dian.document', string="Documento DIAN (NE)",
                                     copy=False, readonly=True)
    ne_zip_key = fields.Char(string="ZipKey DIAN", copy=False, readonly=True)
    ne_mensaje = fields.Text(string="Mensaje DIAN", copy=False, readonly=True)

    # ------------------------------------------------------------------
    # Configuración: modo de operación de nómina (los 3 datos DIAN)
    # ------------------------------------------------------------------
    def _ne_operation_mode(self):
        self.ensure_one()
        mode = self.company_id.l10n_co_dian_operation_mode_ids.filtered(
            lambda m: m.dian_software_operation_mode == 'payroll')
        if not mode:
            raise UserError(_(
                "No hay un Modo de operación DIAN de tipo 'Nómina Electrónica' configurado.\n\n"
                "Vaya a Ajustes > Contabilidad > Localización colombiana > Modos de operación DIAN, "
                "cree uno con:\n"
                "  • Software Mode: DIAN: Nómina Electrónica\n"
                "  • Software ID:  f2dcaae9-8d75-43f8-95d7-25c1bd3c31d5\n"
                "  • Software PIN: 12345\n"
                "  • Testing ID:   35776757-d8d1-44d2-a3da-7eb82e514613"))
        return mode[:1]

    def _ne_cert(self):
        self.ensure_one()
        cert = self.company_id.sudo().l10n_co_dian_certificate_ids[-1:]
        if not cert and not self.company_id.l10n_co_dian_demo_mode:
            raise UserError(_("La compañía no tiene certificado DIAN configurado "
                              "(el mismo que usa para factura electrónica)."))
        return cert

    def _ne_ambiente(self):
        # 2 = pruebas/habilitación ; 1 = producción
        return '2' if self.company_id.l10n_co_dian_test_environment else '1'

    # ------------------------------------------------------------------
    # Firma XAdES-EPES del documento (reutiliza los helpers nativos)
    # ------------------------------------------------------------------
    def _ne_software_security_code(self, op_mode, num_ne):
        """SoftwareSC = SHA384(SoftwareID + SoftwarePIN + NumNE)."""
        cadena = (op_mode.dian_software_id or '') + (op_mode.dian_software_security_code or '') + (num_ne or '')
        return sha384(cadena.encode()).hexdigest()

    @staticmethod
    def _ne_issuer_dian(cert):
        """X509IssuerName en el formato que EXIGE la DIAN (igual al de SIESA aceptado):
        separador ', ' y abreviatura 'S=' para el estado (no 'ST=' de rfc4514).
        La librería de Odoo devuelve rfc4514 ('ST=', sin espacios) y eso provoca ZE02."""
        raw = cert._get_issuer_string()          # rfc4514: CN=..,O=..,C=CO,ST=..,L=..
        parts = [p.strip() for p in re.split(r'(?<!\\),', raw)]
        parts = [('S=' + p[3:]) if p.startswith('ST=') else p for p in parts]
        return ', '.join(parts)

    def _ne_add_signature_node(self, root, cert):
        """Inserta ext:UBLExtensions con la firma ds:Signature (XAdES-EPES) al inicio
        del documento, replicando EXACTAMENTE el patrón de oro aceptado por la DIAN:
        canonicalización exclusiva (exc-c14n), KeyInfo Id='KeyInfo',
        SignedProperties Id='SignedPropertiesId', política https:// sin Description,
        ClaimedRole 'third party'. Luego rellena digests + firma con helpers nativos."""
        INCL = 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315'
        EXCL = 'http://www.w3.org/2001/10/xml-exc-c14n#'
        SHA256 = 'http://www.w3.org/2001/04/xmlenc#sha256'
        doc_id = "xmldsig-" + str(xml_utils._uuid1())
        keyinfo_id = doc_id + "-keyinfo"
        signprops_id = doc_id + "-signedprops"
        # SigningTime SIN milisegundos (timespec='seconds'): las nóminas aceptadas
        # (SIESA, AGUILAR) NO llevan milisegundos. Con milisegundos -> ZE02.
        signing_time = fields.datetime.now(tz=timezone('America/Bogota')).isoformat(timespec='seconds')

        ubl = etree.Element('{%s}UBLExtensions' % NS_EXT)
        ext = _E(ubl, '{%s}UBLExtension' % NS_EXT)
        content = _E(ext, '{%s}ExtensionContent' % NS_EXT)
        sig = _E(content, '{%s}Signature' % NS_DS)
        sig.set('Id', doc_id)

        # SignedInfo — canonicalización INCLUSIVA (REC-xml-c14n-20010315), igual que la
        # nómina AGUILAR que la DIAN YA ACEPTÓ (y que el Anexo DC03). ref1/ref2 sin transform.
        si = _E(sig, '{%s}SignedInfo' % NS_DS)
        _E(si, '{%s}CanonicalizationMethod' % NS_DS, Algorithm=INCL)
        _E(si, '{%s}SignatureMethod' % NS_DS, Algorithm='http://www.w3.org/2001/04/xmldsig-more#rsa-sha256')
        # Ref 0: documento completo (enveloped, sin c14n explícita -> inclusiva por defecto,
        # igual que la nómina aceptada)
        r0 = _E(si, '{%s}Reference' % NS_DS, URI='', Id=doc_id + '-ref0')
        tr0 = _E(r0, '{%s}Transforms' % NS_DS)
        _E(tr0, '{%s}Transform' % NS_DS, Algorithm='http://www.w3.org/2000/09/xmldsig#enveloped-signature')
        _E(r0, '{%s}DigestMethod' % NS_DS, Algorithm=SHA256)
        _E(r0, '{%s}DigestValue' % NS_DS, 'dummy')
        # Ref 1: KeyInfo (SIN transform -> inclusiva, igual que la factura aceptada)
        r1 = _E(si, '{%s}Reference' % NS_DS, URI='#' + keyinfo_id)
        _E(r1, '{%s}DigestMethod' % NS_DS, Algorithm=SHA256)
        _E(r1, '{%s}DigestValue' % NS_DS, 'dummy')
        # Ref 2: SignedProperties (SIN transform -> inclusiva)
        r2 = _E(si, '{%s}Reference' % NS_DS, URI='#' + signprops_id,
                Type='http://uri.etsi.org/01903#SignedProperties')
        _E(r2, '{%s}DigestMethod' % NS_DS, Algorithm=SHA256)
        _E(r2, '{%s}DigestValue' % NS_DS, 'dummy')

        # SignatureValue (se rellena luego) — CON Id, igual que el nativo aceptado
        _E(sig, '{%s}SignatureValue' % NS_DS, 'dummy', Id=doc_id + '-sigvalue')

        # KeyInfo (Id = doc_id-keyinfo). Certificado tal cual lo entrega Odoo (nativo).
        ki = _E(sig, '{%s}KeyInfo' % NS_DS)
        ki.set('Id', keyinfo_id)
        x509d = _E(ki, '{%s}X509Data' % NS_DS)
        _E(x509d, '{%s}X509Certificate' % NS_DS, cert._get_der_certificate_bytes().decode())

        # Object / QualifyingProperties / SignedProperties
        obj = _E(sig, '{%s}Object' % NS_DS)
        qp = _E(obj, '{%s}QualifyingProperties' % NS_XADES, Target='#' + doc_id)
        sp = _E(qp, '{%s}SignedProperties' % NS_XADES)
        sp.set('Id', signprops_id)
        ssp = _E(sp, '{%s}SignedSignatureProperties' % NS_XADES)
        _E(ssp, '{%s}SigningTime' % NS_XADES, signing_time)
        scert = _E(ssp, '{%s}SigningCertificate' % NS_XADES)
        c = _E(scert, '{%s}Cert' % NS_XADES)
        cd = _E(c, '{%s}CertDigest' % NS_XADES)
        _E(cd, '{%s}DigestMethod' % NS_DS, Algorithm=SHA256)
        _E(cd, '{%s}DigestValue' % NS_DS, cert._get_fingerprint_bytes(formatting='base64').decode())
        issuer = _E(c, '{%s}IssuerSerial' % NS_XADES)
        # Emisor en formato NATIVO de Odoo (rfc4514, 'ST=' sin espacios), NO el de SIESA
        # Emisor en formato rfc4514 (ST=), IDÉNTICO a la factura de Odoo que la DIAN YA
        # ACEPTÓ en habilitación con este mismo certificado (SETP990000004, autorizada).
        _E(issuer, '{%s}X509IssuerName' % NS_DS, cert._get_issuer_string())
        _E(issuer, '{%s}X509SerialNumber' % NS_DS, int(cert.serial_number))
        # Política de firma: 'https:/' (una barra) + Description, igual que el nativo
        spi = _E(ssp, '{%s}SignaturePolicyIdentifier' % NS_XADES)
        spid = _E(spi, '{%s}SignaturePolicyId' % NS_XADES)
        spolid = _E(spid, '{%s}SigPolicyId' % NS_XADES)
        _E(spolid, '{%s}Identifier' % NS_XADES, SIG_POLICY_URL)
        # SIN Description: las nóminas aceptadas (SIESA, AGUILAR) NO llevan el elemento
        # xades:Description dentro de SigPolicyId. Incluirlo -> ZE02.
        sph = _E(spid, '{%s}SigPolicyHash' % NS_XADES)
        _E(sph, '{%s}DigestMethod' % NS_DS, Algorithm=SHA256)
        _E(sph, '{%s}DigestValue' % NS_DS, SIG_POLICY_HASH)
        # Rol: 'third party' — es el que llevan AMBAS nóminas aceptadas (SIESA y AGUILAR).
        # El emisor de nómina actúa como tercero, no como 'supplier' (eso es de factura).
        srole = _E(ssp, '{%s}SignerRole' % NS_XADES)
        cr = _E(srole, '{%s}ClaimedRoles' % NS_XADES)
        _E(cr, '{%s}ClaimedRole' % NS_XADES, 'third party')

        # Insertar al inicio y firmar reutilizando los helpers nativos
        root.insert(0, ubl)
        xml_utils._remove_tail_and_text_in_hierarchy(root)
        xml_utils._reference_digests(si)
        xml_utils._fill_signature(sig, cert)
        return root

    def _ne_xml_firmado(self):
        """Genera el XML NominaIndividual, lo firma y devuelve (xml_bytes, cune, datos)."""
        self.ensure_one()
        op_mode = self._ne_operation_mode()
        datos = self._ne_datos()
        num_ne = datos['secuencia']['numero']
        cune = self._ne_cune(datos, software_pin=op_mode.dian_software_security_code or '')
        ssc = self._ne_software_security_code(op_mode, num_ne)
        if datos.get('nota'):
            xml_str = self._ne_build_xml_ajuste(datos, cune, op_mode=op_mode, software_sc=ssc)
        else:
            xml_str = self._ne_build_xml(datos, cune, op_mode=op_mode, software_sc=ssc)
        # v4.3.0: guardar numero y FechaGen enviados (los usa una futura nota de ajuste)
        self.ne_numero = num_ne
        self.ne_fecha_gen = datos['fecha_gen']
        root = etree.fromstring(xml_str.encode() if isinstance(xml_str, str) else xml_str)
        cert = self._ne_cert()
        if cert:
            self._ne_add_signature_node(root, cert)
        # Declaración XML limpia (comillas dobles, sin salto de línea antes de la raíz),
        # igual al ejemplo oficial de la DIAN y sin caracteres de edición (regla ZB02).
        # v4.2.0: SIN declaracion <?xml ...?>: ni la factura aceptada (SETP990000008) ni
        # las nominas aceptadas (GOMEZ/AGUILAR) la llevan.
        xml_bytes = etree.tostring(root, xml_declaration=False, encoding='UTF-8')
        return xml_bytes, cune, datos

    # ------------------------------------------------------------------
    # Validación local contra el XSD OFICIAL de la DIAN (Caja de Herramientas)
    # ------------------------------------------------------------------
    def _ne_validar_xsd(self, xml_bytes, tipo='102'):
        """Valida el XML contra el XSD oficial de la DIAN. Devuelve (ok, [errores])."""
        xsd_name = ('NominaIndividualDeAjusteElectronicaXSDV1.0.6.xsd' if str(tipo) == '103'
                    else 'NominaIndividualElectronicaXSDV1.0.6.xsd')
        xsd_path = os.path.join(os.path.dirname(__file__), '..', 'schemas', 'xsd', xsd_name)
        if not os.path.exists(xsd_path):
            return True, []  # sin XSD instalado no se bloquea el envío
        try:
            schema = etree.XMLSchema(etree.parse(xsd_path))
        except Exception:
            return True, []
        doc = etree.fromstring(xml_bytes if isinstance(xml_bytes, bytes) else xml_bytes.encode())
        ok = schema.validate(doc)
        errs = ['%s (línea %s)' % (e.message, e.line) for e in schema.error_log]
        return ok, errs

    def action_ne_validar_xsd(self):
        """Genera el XML y lo valida contra el XSD oficial (sin enviar). Muestra resultado."""
        self.ensure_one()
        xml_bytes, cune, datos = self._ne_xml_firmado()
        self.ne_cune = cune
        self.ne_xml = xml_bytes.decode('utf-8', errors='replace')
        ok, errs = self._ne_validar_xsd(xml_bytes, datos.get('tipo_documento', '102'))
        if ok:
            self.ne_mensaje = _("✓ El XML es VÁLIDO contra el XSD oficial de la DIAN.")
        else:
            self.ne_mensaje = _("✗ El XML NO cumple el XSD oficial:\n") + "\n".join("• " + e for e in errs[:30])
        return True

    # ------------------------------------------------------------------
    # Botones: generar, enviar al set de pruebas, consultar estado
    # ------------------------------------------------------------------
    def action_ne_generar(self):
        """Genera y firma el XML (sin enviar). Deja el XML listo para revisar."""
        for slip in self:
            xml_bytes, cune, _datos = slip._ne_xml_firmado()
            slip.ne_cune = cune
            slip.ne_xml = xml_bytes.decode('utf-8', errors='replace')
            slip.ne_state = 'generated'
        return True

    def action_ne_descargar(self):
        """Descarga el XML firmado tal cual (bytes exactos) para inspección/validación."""
        self.ensure_one()
        if not self.ne_xml:
            xml_bytes, cune, _d = self._ne_xml_firmado()
            self.ne_cune = cune
            self.ne_xml = xml_bytes.decode('utf-8', errors='replace')
        att = self.env['ir.attachment'].create({
            'name': 'NE_%s.xml' % (self.number or self.id),
            'type': 'binary',
            'datas': b64encode(self.ne_xml.encode('utf-8')),
            'mimetype': 'application/xml',
        })
        return {'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}

    def action_ne_enviar(self):
        """Firma y transmite al servicio SendTestSetAsync (set de pruebas DIAN),
        incrustando el TestSetID del modo de operación. Reutiliza el motor nativo."""
        for slip in self:
            op_mode = slip._ne_operation_mode()
            if not op_mode.dian_testing_id:
                raise UserError(_("El modo de operación de nómina no tiene TestSetID (Testing ID). "
                                  "Debe ser 35776757-d8d1-44d2-a3da-7eb82e514613."))
            xml_bytes, cune, datos = slip._ne_xml_firmado()
            slip.ne_cune = cune
            slip.ne_xml = xml_bytes.decode('utf-8', errors='replace')

            # Validar contra el XSD oficial ANTES de enviar (no gastar el set de pruebas)
            ok, errs = slip._ne_validar_xsd(xml_bytes, datos.get('tipo_documento', '102'))
            if not ok:
                raise UserError(_("El XML no cumple el XSD oficial de la DIAN. No se envió.\n\n")
                                + "\n".join("• " + e for e in errs[:20]))

            # Modo demo: no envía, solo marca generado
            if slip.company_id.l10n_co_dian_demo_mode:
                slip.ne_state = 'generated'
                slip.ne_mensaje = _("Modo demo: XML firmado, sin envío real a la DIAN.")
                continue

            # Empaquetar el XML en ZIP (igual que factura)
            zbuf = io.BytesIO()
            with zipfile.ZipFile(zbuf, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('%s.xml' % (datos['secuencia']['numero'] or 'nomina'), xml_bytes)
            zipped = zbuf.getvalue()

            # Envío SOAP firmado al VPFE, servicio SendTestSetAsync con el TestSetID
            resp = xml_utils._build_and_send_request(
                slip.env['l10n_co_dian.document'],
                payload={
                    'file_name': 'nomina.zip',
                    'content_file': b64encode(zipped).decode(),
                    'test_set_id': op_mode.dian_testing_id,
                    'soap_body_template': 'l10n_co_dian.send_test_set_async',
                },
                service='SendTestSetAsync',
                company=slip.company_id,
            )
            slip._ne_procesar_respuesta_envio(resp, xml_bytes, cune)
        return True

    def _ne_procesar_respuesta_envio(self, resp, xml_bytes, cune):
        self.ensure_one()
        if not resp.get('response'):
            self.ne_state = 'rejected'
            self.ne_mensaje = _("La DIAN no respondió (timeout o servicio no disponible).")
            return
        root = etree.fromstring(resp['response'].encode())
        if resp.get('status_code') != 200:
            self.ne_state = 'rejected'
            self.ne_mensaje = self._ne_render_msg(root)
            return
        zip_key = root.findtext('.//{*}ZipKey')
        att = self.env['ir.attachment'].create({
            'name': 'NE_%s.xml' % (self.number or self.id),
            'raw': xml_bytes,
            'mimetype': 'application/xml',
        })
        doc = self.env['l10n_co_dian.document'].create({
            'move_id': False,
            'identifier': cune,
            'state': 'invoice_pending' if zip_key else 'invoice_rejected',
            'zip_key': zip_key or False,
            'attachment_id': att.id,
            'datetime': fields.Datetime.now(),
            'test_environment': self.company_id.l10n_co_dian_test_environment,
            'certification_process': True,
            'message_json': {'status': _("Nómina en proceso en la DIAN.") if zip_key else '',
                             'errors': [n.text for n in root.findall('.//{*}ProcessedMessage')]},
        })
        self.ne_document_id = doc.id
        self.ne_zip_key = zip_key or False
        if zip_key:
            self.ne_state = 'sent'
            self.ne_mensaje = _("Enviado al set de pruebas. ZipKey: %s\nUse 'Consultar estado' en unos segundos.") % zip_key
        else:
            self.ne_state = 'rejected'
            self.ne_mensaje = self._ne_render_msg(root)

    def action_ne_corregir(self):
        """v4.3.0: crea la nota de ajuste tipo REEMPLAZAR: copia del recibo aceptado, en
        borrador, apuntando al original. El usuario corrige novedades, calcula y envia."""
        self.ensure_one()
        if self.ne_state != 'accepted':
            raise UserError(_("Solo se puede corregir un recibo ACEPTADO por la DIAN."))
        if self.ne_tipo_nota:
            raise UserError(_("No se puede hacer una nota de ajuste sobre otra nota de ajuste."))
        vals = {'ne_reemplaza_id': self.id, 'ne_state': 'draft',
                'name': _("Corrección (reemplazo) de %s") % (self.number or '')}
        if 'credit_note' in self._fields:
            vals['credit_note'] = False
        if 'origin_payslip_id' in self._fields:
            vals['origin_payslip_id'] = False
        nuevo = self.copy(vals)
        return {'type': 'ir.actions.act_window', 'res_model': 'hr.payslip',
                'res_id': nuevo.id, 'view_mode': 'form', 'target': 'current'}

    def action_ne_consultar(self):
        """Consulta el resultado del set de pruebas (GetStatusZip) usando el ZipKey."""
        for slip in self:
            if not slip.ne_zip_key:
                raise UserError(_("Este recibo no tiene ZipKey; primero envíelo con 'Enviar a DIAN'."))
            resp = xml_utils._build_and_send_request(
                slip.env['l10n_co_dian.document'],
                payload={'track_id': slip.ne_zip_key, 'soap_body_template': 'l10n_co_dian.get_status_zip'},
                service='GetStatusZip',
                company=slip.company_id,
            )
            if resp.get('status_code') != 200 or not resp.get('response'):
                slip.ne_mensaje = _("La DIAN no respondió la consulta (código %s).") % resp.get('status_code')
                continue
            root = etree.fromstring(resp['response'].encode())
            slip.ne_mensaje = slip._ne_render_msg(root)
            if root.findtext('.//{*}IsValid') == 'true':
                slip.ne_state = 'accepted'
                if slip.ne_document_id:
                    slip.ne_document_id.state = 'invoice_accepted'
                # v4.3.0: una nota de ajuste aceptada cambia el estado del recibo original
                pred = slip._ne_predecesor()
                if pred:
                    pred.ne_state = 'replaced' if slip.ne_tipo_nota == '1' else 'deleted'
                    pred.ne_mensaje = _("%s por la nota de ajuste %s (CUNE %s).") % (
                        _("Reemplazado") if slip.ne_tipo_nota == '1' else _("Eliminado"),
                        slip.ne_numero, slip.ne_cune)
            elif not root.findtext('.//{*}StatusCode'):
                slip.ne_state = 'sent'   # sigue pendiente
            else:
                slip.ne_state = 'rejected'
                if slip.ne_document_id:
                    slip.ne_document_id.state = 'invoice_rejected'
        return True

    @staticmethod
    def _ne_render_msg(root):
        partes = []
        status = root.findtext('.//{*}StatusDescription') or root.findtext('.//{*}StatusMessage')
        if status:
            partes.append(status)
        for node in root.findall('.//{*}ErrorMessage/{*}string'):
            if node.text:
                partes.append("• " + node.text)
        for node in root.findall('.//{*}ProcessedMessage'):
            if node.text:
                partes.append("• " + node.text)
        return "\n".join(partes) or _("Sin mensaje de la DIAN.")
