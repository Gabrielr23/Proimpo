# -*- coding: utf-8 -*-
import io
import base64
from odoo import models, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _pila_line(self, code):
        self.ensure_one()
        return sum(self.line_ids.filtered(lambda l: l.salary_rule_id.code == code).mapped('total'))

    def action_reporte_datos_pila(self):
        """Reporte Excel con los datos de PILA por empleado, consolidando el mes
        (todas las quincenas seleccionadas). Para validar contra el operador."""
        if xlsxwriter is None:
            raise UserError(_("Falta la librería xlsxwriter en el servidor."))
        slips = self.filtered(lambda s: s.state in ('done', 'paid')) or self
        if not slips:
            raise UserError(_("No hay recibos válidos."))

        # Consolidar por empleado
        emp = {}
        for s in slips:
            e = s.employee_id
            d = emp.setdefault(e.id, {
                'emp': e, 'contract': s.contract_id,
                'ibc': 0.0, 'pension': 0.0, 'salud': 0.0, 'arl': 0.0, 'ccf': 0.0,
                'sena': 0.0, 'icbf': 0.0, 'fsp': 0.0,
                'dias': 0.0,
            })
            d['ibc'] += s._pila_line('IBC') + s._pila_line('IBCAPR')
            d['pension'] += abs(s._pila_line('PENS')) + s._pila_line('APPENS')
            d['salud'] += abs(s._pila_line('SALUD')) + s._pila_line('APSALUD') + s._pila_line('APSALUDAPR')
            d['arl'] += s._pila_line('APARL') + s._pila_line('APARLAPR')
            d['ccf'] += s._pila_line('APCCF')
            d['sena'] += s._pila_line('APSENA')
            d['icbf'] += s._pila_line('APICBF')
            d['fsp'] += abs(s._pila_line('FSP'))
            d['dias'] += s._dias_cotizados_pila()

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('PILA')
        navy = '#1F4E79'
        f_t = wb.add_format({'bold': True, 'font_size': 13, 'font_color': navy})
        f_h = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': navy, 'border': 1,
                             'text_wrap': True, 'align': 'center', 'valign': 'vcenter'})
        f_x = wb.add_format({'border': 1, 'font_size': 9})
        f_n = wb.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 9})
        f_tot = wb.add_format({'border': 1, 'num_format': '#,##0', 'bold': True, 'bg_color': '#DDEBF7'})

        ws.write(0, 0, "Datos PILA (consolidado del mes) — validación", f_t)
        hdr = ['Cédula', 'Empleado', 'T.Cot', 'Sub', 'Municipio', 'EPS', 'AFP', 'ARL', 'Caja',
               'Días', 'IBC', 'Cotiz. Pensión', 'Cotiz. Salud', 'Cotiz. ARL', 'Cotiz. Caja',
               'Cotiz. SENA', 'Cotiz. ICBF', 'FSP']
        for c, h in enumerate(hdr):
            ws.write(2, c, h, f_h)
        r = 3
        tot = [0.0] * len(hdr)
        for d in sorted(emp.values(), key=lambda x: (x['emp'].name or '')):
            e = d['emp']; ct = d['contract']
            tw = ct.type_worker_id.code if ct.type_worker_id else ''
            sw = ct.subtype_worker_id.code if ct.subtype_worker_id else ''
            vals = [e.identification_id or '', e.name or '', tw, sw,
                    ct.pila_municipio_code or '', ct.pila_eps_code or '', ct.pila_afp_code or '',
                    ct.pila_arl_code or '', ct.pila_ccf_code or '',
                    round(d['dias']), round(d['ibc']), round(d['pension']), round(d['salud']),
                    round(d['arl']), round(d['ccf']), round(d['sena']), round(d['icbf']), round(d['fsp'])]
            for c, v in enumerate(vals):
                if c >= 9:
                    ws.write(r, c, v, f_n); tot[c] += v
                else:
                    ws.write(r, c, v, f_x)
            r += 1
        ws.write(r, 0, 'TOTALES', f_tot)
        for c in range(1, 9):
            ws.write(r, c, '', f_tot)
        for c in range(9, len(hdr)):
            ws.write(r, c, tot[c], f_tot)
        for c, w in [(0, 13), (1, 30), (5, 9), (6, 9), (7, 8), (8, 8)]:
            ws.set_column(c, c, w)
        ws.set_column(9, len(hdr) - 1, 13)
        ws.freeze_panes(3, 2)
        wb.close(); output.seek(0)
        att = self.env['ir.attachment'].create({
            'name': 'Datos_PILA.xlsx', 'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}
