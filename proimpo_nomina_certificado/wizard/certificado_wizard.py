# -*- coding: utf-8 -*-
import io
import base64
from datetime import date
from odoo import models, fields, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

CAS_ING = [('36', 'Salarios'), ('37', 'Bonos'), ('38', 'Honorarios'), ('39', 'Servicios'),
           ('40', 'Comisiones'), ('41', 'Prestaciones'), ('42', 'Viaticos'),
           ('43', 'Gastos rep.'), ('44', 'Coop.'), ('45', 'Otros pagos'),
           ('46', 'Ces/Int pagadas'), ('47', 'Ces. consignadas'), ('48', 'Pensiones'),
           ('49', 'TOTAL INGRESOS')]
CAS_APO = [('50', 'Salud'), ('51', 'Pension+FSP'), ('52', 'RAIS'), ('53', 'APV'),
           ('54', 'AFC/AVC'), ('55', 'Retencion')]


class CertificadoIngresosWizard(models.TransientModel):
    _name = 'certificado.ingresos.wizard'
    _description = 'Certificado de ingresos y retenciones (220)'

    anio = fields.Integer(string="Ano gravable", required=True,
                          default=lambda s: date.today().year - 1)
    smmlv = fields.Float(string="SMMLV del ano", required=True,
                         default=lambda s: s.env.company.smmlv_value or 0.0)
    aux_transporte = fields.Float(string="Auxilio de transporte del ano", required=True, default=1)
    employee_ids = fields.Many2many('hr.employee', string="Empleados",
                                    help="Vacio = todos los empleados con nomina en el ano.")

    def _empleados(self):
        if self.employee_ids:
            return self.employee_ids
        ini = date(self.anio, 1, 1); fin = date(self.anio, 12, 31)
        slips = self.env['hr.payslip'].search([
            ('state', 'in', ('done', 'paid')),
            ('date_from', '>=', ini), ('date_to', '<=', fin)])
        return slips.mapped('employee_id')

    def action_generar_pdf(self):
        emps = self._empleados()
        if not emps:
            raise UserError(_("No hay empleados con nomina en el ano %s.") % self.anio)
        data = {'anio': self.anio, 'smmlv': self.smmlv, 'aux': self.aux_transporte,
                'emp_ids': emps.ids}
        return self.env.ref('proimpo_nomina_certificado.action_report_cert220').with_context(
            discard_logo_check=True).report_action(emps.ids, data=data)

    def action_generar_excel(self):
        if xlsxwriter is None:
            raise UserError(_("Falta la libreria xlsxwriter en el servidor."))
        emps = self._empleados()
        if not emps:
            raise UserError(_("No hay empleados con nomina en el ano %s.") % self.anio)
        rep = self.env['report.proimpo_nomina_certificado.cert220_document']
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Certificado 220 %s' % self.anio)
        navy = '#1F4E79'
        f_t = wb.add_format({'bold': True, 'font_size': 13, 'font_color': navy})
        f_h = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': navy, 'border': 1,
                             'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        f_x = wb.add_format({'border': 1, 'font_size': 9})
        f_n = wb.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 9})
        f_tt = wb.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 9, 'bold': True,
                              'bg_color': '#DDEBF7'})
        ws.write(0, 0, "Certificado de ingresos y retenciones (F220) - ano %s" % self.anio, f_t)
        cols = ['Cedula', 'Empleado'] + ['%s-%s' % (k, n) for k, n in CAS_ING] + \
               ['%s-%s' % (k, n) for k, n in CAS_APO]
        for c, h in enumerate(cols):
            ws.write(2, c, h, f_h)
        r = 3
        for e in sorted(emps, key=lambda x: x.name or ''):
            cas = rep._casillas_empleado(e, self.anio, self.smmlv, self.aux_transporte)
            ws.write(r, 0, e.identification_id or '', f_x)
            ws.write(r, 1, e.name or '', f_x)
            c = 2
            for k, _n in CAS_ING:
                fmt = f_tt if k == '49' else f_n
                ws.write(r, c, cas.get(k, 0), fmt); c += 1
            for k, _n in CAS_APO:
                ws.write(r, c, cas.get(k, 0), f_n); c += 1
            r += 1
        ws.set_column(0, 0, 13); ws.set_column(1, 1, 30); ws.set_column(2, len(cols) - 1, 13)
        ws.freeze_panes(3, 2)
        wb.close(); output.seek(0)
        att = self.env['ir.attachment'].create({
            'name': 'Certificado220_control_%s.xlsx' % self.anio, 'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        return {'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}
