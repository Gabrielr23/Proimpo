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

    def _rc_grupo(self, rule):
        """Clasifica una regla: dev / ded / apo (aporte patronal) / pro (provisión) / None."""
        tc = rule.type_concept
        if tc == 'earn':
            return 'dev'
        if tc == 'deduction':
            return 'ded'
        catn = (rule.category_id.name or '').lower()
        if 'aporte' in catn or 'patronal' in catn:
            return 'apo'
        if 'provi' in catn:
            return 'pro'
        return None

    def action_reporte_columnar(self):
        """Excel columnar con TODOS los conceptos (devengados, deducciones,
        aportes patronales y provisiones), un empleado por fila."""
        if xlsxwriter is None:
            raise UserError(_("Falta la librería xlsxwriter en el servidor."))
        # Acepta uno o varios lotes: combina los recibos de todos los seleccionados
        slips = self.mapped('slip_ids')
        if not slips:
            raise UserError(_("Los lotes seleccionados no tienen recibos."))

        reglas = {}
        for s in slips:
            for l in s.line_ids:
                r = l.salary_rule_id
                g = self._rc_grupo(r)
                if g:
                    reglas.setdefault(r.code, {'name': r.name, 'seq': r.sequence, 'g': g})
        dev = sorted([c for c, v in reglas.items() if v['g'] == 'dev'], key=lambda c: reglas[c]['seq'])
        ded = sorted([c for c, v in reglas.items() if v['g'] == 'ded'], key=lambda c: reglas[c]['seq'])
        apo = sorted([c for c, v in reglas.items() if v['g'] == 'apo'], key=lambda c: reglas[c]['seq'])
        pro = sorted([c for c, v in reglas.items() if v['g'] == 'pro'], key=lambda c: reglas[c]['seq'])

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Nómina')
        ws.freeze_panes(4, 4)
        navy = '#1F4E79'
        f_title = wb.add_format({'bold': True, 'font_size': 13, 'font_color': navy})
        f_sub = wb.add_format({'font_size': 9, 'font_color': '#666666'})
        f_hdr = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': navy,
                               'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        f_sec = wb.add_format({'bold': True, 'font_color': navy, 'bg_color': '#DDEBF7',
                               'border': 1, 'align': 'center'})
        f_txt = wb.add_format({'border': 1, 'font_size': 9})
        f_num = wb.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 9})
        f_tot = wb.add_format({'border': 1, 'num_format': '#,##0', 'bold': True, 'bg_color': '#DDEBF7'})
        f_totlbl = wb.add_format({'border': 1, 'bold': True, 'bg_color': '#DDEBF7'})

        empresa = (self[:1].company_id.name or '')
        lotes_txt = ", ".join(self.mapped('name'))
        fechas = [d for d in self.mapped('date_start') if d] + [d for d in self.mapped('date_end') if d]
        per_ini = min(self.mapped('date_start')) if self.mapped('date_start') else ''
        per_fin = max(self.mapped('date_end')) if self.mapped('date_end') else ''
        ws.write(0, 0, "%s — Reporte columnar de nómina" % empresa, f_title)
        ws.write(1, 0, "Lote(s): %s   Período: %s a %s" % (lotes_txt, per_ini, per_fin), f_sub)

        # Fila 2: bandas de sección; Fila 3: encabezados de columna
        fijas = ['Cédula', 'Empleado', 'Cargo', 'C. Costo']
        col = 0
        for h in fijas:
            ws.write(3, col, h, f_hdr)
            ws.write(2, col, '', f_hdr)
            col += 1

        def banda(ini, fin, texto):
            if fin > ini:
                if fin - 1 > ini:
                    ws.merge_range(2, ini, 2, fin - 1, texto, f_sec)
                else:
                    ws.write(2, ini, texto, f_sec)

        dev_start = col
        for c in dev:
            ws.write(3, col, reglas[c]['name'], f_hdr); col += 1
        banda(dev_start, col, 'DEVENGADOS')
        col_totdev = col; ws.write(3, col, 'TOTAL DEVENGADO', f_hdr); ws.write(2, col, '', f_sec); col += 1
        ded_start = col
        for c in ded:
            ws.write(3, col, reglas[c]['name'], f_hdr); col += 1
        banda(ded_start, col, 'DEDUCCIONES')
        col_totded = col; ws.write(3, col, 'TOTAL DEDUCCIÓN', f_hdr); ws.write(2, col, '', f_sec); col += 1
        col_neto = col; ws.write(3, col, 'NETO', f_hdr); ws.write(2, col, '', f_sec); col += 1
        apo_start = col
        for c in apo:
            ws.write(3, col, reglas[c]['name'], f_hdr); col += 1
        banda(apo_start, col, 'APORTES PATRONALES')
        pro_start = col
        for c in pro:
            ws.write(3, col, reglas[c]['name'], f_hdr); col += 1
        banda(pro_start, col, 'PROVISIONES')
        ncols = col

        def val(s, code):
            return sum(s.line_ids.filtered(lambda l: l.salary_rule_id.code == code).mapped('total'))

        totales = [0.0] * ncols
        r = 4
        for s in slips.sorted(key=lambda x: (x.employee_id.name or '')):
            emp = s.employee_id
            ws.write(r, 0, emp.identification_id or '', f_txt)
            ws.write(r, 1, emp.name or '', f_txt)
            ws.write(r, 2, emp.job_id.name or '', f_txt)
            ws.write(r, 3, emp.department_id.name or '', f_txt)
            tot_dev = 0.0
            c = dev_start
            for code in dev:
                v = val(s, code); ws.write(r, c, v, f_num); totales[c] += v; tot_dev += v; c += 1
            ws.write(r, col_totdev, tot_dev, f_num); totales[col_totdev] += tot_dev
            tot_ded = 0.0
            c = ded_start
            for code in ded:
                v = -val(s, code); ws.write(r, c, v, f_num); totales[c] += v; tot_ded += v; c += 1
            ws.write(r, col_totded, tot_ded, f_num); totales[col_totded] += tot_ded
            neto = tot_dev - tot_ded
            ws.write(r, col_neto, neto, f_num); totales[col_neto] += neto
            c = apo_start
            for code in apo:
                v = val(s, code); ws.write(r, c, v, f_num); totales[c] += v; c += 1
            c = pro_start
            for code in pro:
                v = val(s, code); ws.write(r, c, v, f_num); totales[c] += v; c += 1
            r += 1

        ws.write(r, 0, 'TOTALES', f_totlbl)
        ws.write(r, 1, '%d empleados' % len(slips), f_totlbl)
        ws.write(r, 2, '', f_totlbl); ws.write(r, 3, '', f_totlbl)
        for c in range(dev_start, ncols):
            ws.write(r, c, totales[c], f_tot)

        ws.set_column(0, 0, 13); ws.set_column(1, 1, 30); ws.set_column(2, 2, 22); ws.set_column(3, 3, 14)
        ws.set_column(4, ncols - 1, 13)
        wb.close(); output.seek(0)
        att = self.env['ir.attachment'].create({
            'name': 'Nomina_columnar_%s.xlsx' % ("_".join(self.mapped('name')) or self.ids and str(self.ids[0]) or 'lote'),
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}
