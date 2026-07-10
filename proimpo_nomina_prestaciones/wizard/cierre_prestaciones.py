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

# Codigos de reglas (ajustables). Provisiones y factores variables/transporte.
PROV = {
    'ces':   ['PROVCES'],
    'int':   ['PROVICES', 'PROVINT', 'PROVICE'],
    'prima': ['PROVPRIMA', 'PROVPRI'],
    'vac':   ['PROVVAC'],
}
COD_TRANSP = ['TRANS', 'AUXTRANS', 'AUXTRANSP']
COD_VAC_PAG = ['VAC', 'VACDISF', 'VACACIONES']
CAT_SALARIAL = 'DEVSAL'          # categoria de devengos salariales
COD_BASICO = ['BASIC', 'BASICO']


def _dias360(d1, d2):
    if not d1 or not d2 or d2 < d1:
        return 0
    a1 = min(d1.day, 30)
    a2 = min(d2.day, 30)
    return (d2.year - d1.year) * 360 + (d2.month - d1.month) * 30 + (a2 - a1) + 1


class CierrePrestacionesWizard(models.TransientModel):
    _name = 'cierre.prestaciones.wizard'
    _description = 'Cierre mensual de prestaciones (consolidado vs provision)'

    fecha_corte = fields.Date(string="Fecha de corte", required=True,
                              default=fields.Date.context_today)
    smmlv = fields.Float(string="SMMLV", required=True,
                         default=lambda s: s.env.company.smmlv_value or 0.0)
    aux_transporte = fields.Float(string="Auxilio de transporte", required=True, default=1)

    # -------- helpers --------
    def _slips(self, ct, d1, d2):
        return self.env['hr.payslip'].search([
            ('contract_id', '=', ct.id), ('state', 'in', ('done', 'paid')),
            ('date_from', '>=', d1), ('date_to', '<=', d2),
        ])

    def _suma_codigos(self, slips, codes):
        if not slips:
            return 0.0
        return sum(slips.mapped('line_ids').filtered(
            lambda l: l.salary_rule_id.code in codes).mapped('total'))

    def _promedio_variable(self, ct, d1, d2):
        """Promedio mensual de factores salariales variables (todo DEVSAL menos basico)."""
        slips = self._slips(ct, d1, d2)
        if not slips:
            return 0.0
        lines = slips.mapped('line_ids').filtered(
            lambda l: l.category_id.code == CAT_SALARIAL and l.salary_rule_id.code not in COD_BASICO)
        var = sum(lines.mapped('total'))
        meses = _dias360(d1, d2) / 30.0
        return var / meses if meses else 0.0

    def _transporte(self, ct):
        if ct.wage > 2 * self.smmlv:
            return 0.0
        return self.aux_transporte

    # -------- motor --------
    def _computar(self):
        self.ensure_one()
        corte = self.fecha_corte
        y = corte.year
        ene1 = date(y, 1, 1)
        sem1 = date(y, 7, 1) if corte.month >= 7 else date(y, 1, 1)
        contratos = self.env['hr.contract'].search([
            ('date_start', '<=', corte),
            '|', ('date_end', '=', False), ('date_end', '>=', ene1),
            ('state', 'in', ('open', 'close')),
        ])
        res = []
        for ct in contratos:
            if ct.integral_salary:
                continue
            emp = ct.employee_id
            d_ano = max(ct.date_start, ene1)
            d_sem = max(ct.date_start, sem1)
            transp = self._transporte(ct)
            prom_ano = self._promedio_variable(ct, d_ano, corte)
            prom_sem = self._promedio_variable(ct, d_sem, corte)

            base_ces = ct.wage + transp + prom_ano
            base_prima = ct.wage + transp + prom_sem
            base_vac = ct.wage + prom_ano          # vacaciones NO incluye transporte

            dias_ano = _dias360(d_ano, corte)
            dias_sem = _dias360(d_sem, corte)
            dias_tot = _dias360(ct.date_start, corte)

            ces = base_ces * dias_ano / 360.0
            interes = ces * dias_ano / 360.0 * 0.12
            prima = base_prima * dias_sem / 360.0
            vac_acum = base_vac * dias_tot / 720.0
            vac_pag = self._suma_codigos(self._slips(ct, ct.date_start, corte), COD_VAC_PAG)
            vac = vac_acum - vac_pag

            slips_ano = self._slips(ct, ene1, corte)
            slips_tot = self._slips(ct, ct.date_start, corte)
            slips_sem = self._slips(ct, sem1, corte)
            p_ces = self._suma_codigos(slips_ano, PROV['ces'])
            p_int = self._suma_codigos(slips_ano, PROV['int'])
            p_pri = self._suma_codigos(slips_sem, PROV['prima'])
            p_vac = self._suma_codigos(slips_tot, PROV['vac'])

            res.append({
                'emp': emp, 'ct': ct,
                'ces': round(ces), 'int': round(interes), 'prima': round(prima), 'vac': round(vac),
                'p_ces': round(p_ces), 'p_int': round(p_int), 'p_pri': round(p_pri), 'p_vac': round(p_vac),
                'base_ces': round(base_ces), 'base_vac': round(base_vac),
                'dias_ano': dias_ano, 'dias_sem': dias_sem, 'dias_tot': dias_tot,
            })
        return res

    def action_generar_reporte(self):
        if xlsxwriter is None:
            raise UserError(_("Falta la libreria xlsxwriter en el servidor."))
        datos = self._computar()
        if not datos:
            raise UserError(_("No hay contratos activos para el corte indicado."))
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Prestaciones')
        navy = '#1F4E79'
        f_t = wb.add_format({'bold': True, 'font_size': 13, 'font_color': navy})
        f_g = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': navy, 'border': 1,
                             'align': 'center', 'valign': 'vcenter'})
        f_h = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#2E75B6', 'border': 1,
                             'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        f_x = wb.add_format({'border': 1, 'font_size': 9})
        f_n = wb.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 9})
        f_a = wb.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 9, 'bg_color': '#FCE4D6'})
        f_tot = wb.add_format({'border': 1, 'num_format': '#,##0', 'bold': True, 'bg_color': '#DDEBF7'})

        ws.write(0, 0, "Cierre de prestaciones al %s (recalculo vs provision)" % self.fecha_corte, f_t)
        # cabecera de dos niveles
        ws.merge_range(2, 0, 3, 0, 'Cedula', f_g)
        ws.merge_range(2, 1, 3, 1, 'Empleado', f_g)
        grupos = [('CESANTIAS', 2), ('INTERESES', 5), ('PRIMA', 8), ('VACACIONES', 11)]
        for nom, c in grupos:
            ws.merge_range(2, c, 2, c + 2, nom, f_g)
        sub = ['Causado', 'Provision', 'Ajuste']
        for _n, c in grupos:
            for i, s in enumerate(sub):
                ws.write(3, c + i, s, f_h)
        r = 4
        T = {k: 0 for k in ['ces', 'int', 'prima', 'vac', 'p_ces', 'p_int', 'p_pri', 'p_vac']}
        for d in sorted(datos, key=lambda x: (x['emp'].name or '')):
            e = d['emp']
            ws.write(r, 0, e.identification_id or '', f_x)
            ws.write(r, 1, e.name or '', f_x)
            bloques = [
                (d['ces'], d['p_ces']), (d['int'], d['p_int']),
                (d['prima'], d['p_pri']), (d['vac'], d['p_vac']),
            ]
            for i, (caus, prov) in enumerate(bloques):
                c = 2 + i * 3
                ws.write(r, c, caus, f_n)
                ws.write(r, c + 1, prov, f_n)
                ws.write(r, c + 2, caus - prov, f_a)
            for k, v in [('ces', d['ces']), ('int', d['int']), ('prima', d['prima']), ('vac', d['vac']),
                         ('p_ces', d['p_ces']), ('p_int', d['p_int']), ('p_pri', d['p_pri']), ('p_vac', d['p_vac'])]:
                T[k] += v
            r += 1
        ws.write(r, 1, 'TOTALES', f_tot)
        tt = [('ces', 'p_ces'), ('int', 'p_int'), ('prima', 'p_pri'), ('vac', 'p_vac')]
        for i, (ck, pk) in enumerate(tt):
            c = 2 + i * 3
            ws.write(r, c, T[ck], f_tot)
            ws.write(r, c + 1, T[pk], f_tot)
            ws.write(r, c + 2, T[ck] - T[pk], f_tot)
        ws.set_column(0, 0, 13); ws.set_column(1, 1, 30); ws.set_column(2, 13, 13)
        ws.freeze_panes(4, 2)
        wb.close(); output.seek(0)
        att = self.env['ir.attachment'].create({
            'name': 'Cierre_Prestaciones_%s.xlsx' % self.fecha_corte, 'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}
