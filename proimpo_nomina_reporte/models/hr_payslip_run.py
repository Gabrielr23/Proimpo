# -*- coding: utf-8 -*-
import io
import base64
from odoo import models, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_reporte_columnar(self):
        """Genera un Excel columnar (empleado x concepto) del lote, para revisión."""
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("Falta la librería xlsxwriter en el servidor."))
        slips = self.slip_ids
        if not slips:
            raise UserError(_("El lote no tiene recibos."))

        # Recolectar conceptos presentes (devengados y deducciones)
        reglas = {}
        for s in slips:
            for l in s.line_ids:
                r = l.salary_rule_id
                if r.type_concept in ('earn', 'deduction'):
                    reglas.setdefault(r.code, {'name': r.name, 'seq': r.sequence, 'tc': r.type_concept})
        dev = sorted([c for c, v in reglas.items() if v['tc'] == 'earn'], key=lambda c: reglas[c]['seq'])
        ded = sorted([c for c, v in reglas.items() if v['tc'] == 'deduction'], key=lambda c: reglas[c]['seq'])

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Nómina')
        ws.freeze_panes(4, 4)

        navy = '#1F4E79'
        f_title = wb.add_format({'bold': True, 'font_size': 13, 'font_color': navy})
        f_sub = wb.add_format({'font_size': 9, 'font_color': '#666666'})
        f_hdr = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': navy,
                               'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        f_txt = wb.add_format({'border': 1, 'font_size': 9})
        f_num = wb.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 9})
        f_tot = wb.add_format({'border': 1, 'num_format': '#,##0', 'bold': True, 'bg_color': '#DDEBF7'})
        f_totlbl = wb.add_format({'border': 1, 'bold': True, 'bg_color': '#DDEBF7'})

        ws.write(0, 0, "%s — Reporte columnar de nómina" % (self.company_id.name or ''), f_title)
        ws.write(1, 0, "Lote: %s   Período: %s a %s" % (self.name or '', self.date_start, self.date_end), f_sub)

        # Encabezados
        fijas = ['Cédula', 'Empleado', 'Cargo', 'C. Costo']
        col = 0
        row_h = 3
        for h in fijas:
            ws.write(row_h, col, h, f_hdr); col += 1
        dev_start = col
        for c in dev:
            ws.write(row_h, col, reglas[c]['name'], f_hdr); col += 1
        col_totdev = col; ws.write(row_h, col, 'TOTAL DEVENGADO', f_hdr); col += 1
        ded_start = col
        for c in ded:
            ws.write(row_h, col, reglas[c]['name'], f_hdr); col += 1
        col_totded = col; ws.write(row_h, col, 'TOTAL DEDUCCIÓN', f_hdr); col += 1
        col_neto = col; ws.write(row_h, col, 'NETO', f_hdr); col += 1
        ncols = col

        # Datos
        def val(s, code):
            return sum(s.line_ids.filtered(lambda l: l.salary_rule_id.code == code).mapped('total'))

        totales = [0.0] * ncols
        r = row_h + 1
        slips_ord = slips.sorted(key=lambda s: (s.employee_id.name or ''))
        for s in slips_ord:
            emp = s.employee_id
            ws.write(r, 0, emp.identification_id or '', f_txt)
            ws.write(r, 1, emp.name or '', f_txt)
            ws.write(r, 2, emp.job_id.name or '', f_txt)
            ws.write(r, 3, emp.department_id.name or '', f_txt)
            c = dev_start
            tot_dev = 0.0
            for code in dev:
                v = val(s, code); ws.write(r, c, v, f_num); totales[c] += v; tot_dev += v; c += 1
            ws.write(r, col_totdev, tot_dev, f_num); totales[col_totdev] += tot_dev
            c = ded_start
            tot_ded = 0.0
            for code in ded:
                v = -val(s, code); ws.write(r, c, v, f_num); totales[c] += v; tot_ded += v; c += 1
            ws.write(r, col_totded, tot_ded, f_num); totales[col_totded] += tot_ded
            neto = tot_dev - tot_ded
            ws.write(r, col_neto, neto, f_num); totales[col_neto] += neto
            r += 1

        # Fila de totales
        ws.write(r, 0, 'TOTALES', f_totlbl)
        ws.write(r, 1, '%d empleados' % len(slips_ord), f_totlbl)
        ws.write(r, 2, '', f_totlbl); ws.write(r, 3, '', f_totlbl)
        for c in range(dev_start, ncols):
            ws.write(r, c, totales[c], f_tot)

        # Anchos
        ws.set_column(0, 0, 13); ws.set_column(1, 1, 30); ws.set_column(2, 2, 22); ws.set_column(3, 3, 14)
        ws.set_column(4, ncols - 1, 13)

        wb.close()
        output.seek(0)
        att = self.env['ir.attachment'].create({
            'name': 'Nomina_columnar_%s.xlsx' % (self.name or self.id),
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % att.id,
            'target': 'self',
        }
