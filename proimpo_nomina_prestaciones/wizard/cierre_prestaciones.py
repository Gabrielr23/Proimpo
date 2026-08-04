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



def _empresa_propia_param(env):
    return env['ir.config_parameter'].sudo().get_param(
        'proimpo_nomina.empresa_propia', 'PROIMPO SAS')


def _dom_empresa_propia(env):
    """Leaf de dominio: procesar solo empleados de la empresa propia (excluye temporales)."""
    if 'x_studio_contrato_con' in env['hr.employee']._fields:
        return [('employee_id.x_studio_contrato_con', '=', _empresa_propia_param(env))]
    return []


def _es_empleado_propio(emp):
    if 'x_studio_contrato_con' not in emp.env['hr.employee']._fields:
        return True
    return emp.x_studio_contrato_con == _empresa_propia_param(emp.env)


class CierrePrestacionesWizard(models.TransientModel):
    _name = 'cierre.prestaciones.wizard'
    _description = 'Cierre mensual de prestaciones (consolidado vs provision)'

    fecha_corte = fields.Date(string="Fecha de corte", required=True,
                              default=fields.Date.context_today)
    smmlv = fields.Float(string="SMMLV", required=True,
                         default=lambda s: s.env.company.smmlv_value or 0.0)
    aux_transporte = fields.Float(string="Auxilio de transporte", required=True, default=1)
    journal_id = fields.Many2one(
        'account.journal', string="Diario",
        default=lambda s: s.env['account.journal'].search(
            ['|', ('name', 'ilike', 'salario'), ('name', 'ilike', 'nomina')], limit=1)
        or s.env['account.journal'].search([('type', '=', 'general')], limit=1),
        help="Diario donde se registra el asiento de ajuste de provisiones.")

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
        ] + _dom_empresa_propia(self.env))
        res = []
        for ct in contratos:
            if ct.integral_salary:
                continue
            emp = ct.employee_id
            # MOTOR UNICO: causado de prestaciones a la fecha de corte
            p = ct._proimpo_prestaciones_causadas(corte, self.smmlv, self.aux_transporte)

            slips_ano = self._slips(ct, ene1, corte)
            slips_tot = self._slips(ct, ct.date_start, corte)
            slips_sem = self._slips(ct, sem1, corte)
            p_ces = self._suma_codigos(slips_ano, PROV['ces'])
            p_int = self._suma_codigos(slips_ano, PROV['int'])
            p_pri = self._suma_codigos(slips_sem, PROV['prima'])
            p_vac = self._suma_codigos(slips_tot, PROV['vac'])

            res.append({
                'emp': emp, 'ct': ct,
                'ces': round(p['ces']), 'int': round(p['int']), 'prima': round(p['prima']), 'vac': round(p['vac']),
                'p_ces': round(p_ces), 'p_int': round(p_int), 'p_pri': round(p_pri), 'p_vac': round(p_vac),
                'base_ces': round(p['base_ces']), 'base_vac': round(p['base_vac']),
                'dias_ano': p['dias_ano'], 'dias_sem': p['dias_sem'], 'dias_tot': p['dias_tot'],
            })
        return res

    def action_generar_asiento(self):
        """Genera un asiento de ajuste de provisiones por empleado (diario Salarios),
        usando las cuentas del mapeo por area."""
        self.ensure_one()
        if not self.journal_id:
            raise UserError(_("Configure el diario del asiento."))
        datos = self._computar()
        Move = self.env['account.move']
        Mapeo = self.env['proimpo.cuenta.mapeo']
        # prestacion -> (nombre, regla de provision, clave causado, clave provision)
        presta = [
            ('Cesantias', 'PROVCES', 'ces', 'p_ces'),
            ('Intereses cesantias', 'PROVINT', 'int', 'p_int'),
            ('Prima', 'PROVPRIMA', 'prima', 'p_pri'),
            ('Vacaciones', 'PROVVAC', 'vac', 'p_vac'),
        ]
        moves = self.env['account.move']
        for d in datos:
            if d.get('error'):
                continue
            ct = d['ct']; emp = d['emp']
            aa = ct.analytic_account_id
            area = aa.proimpo_area if aa else False
            distrib = {str(aa.id): 100.0} if aa else False
            lineas = []
            for nombre, rule_code, k_caus, k_prov in presta:
                ajuste = round((d.get(k_caus, 0) or 0) - (d.get(k_prov, 0) or 0))
                if not ajuste:
                    continue
                mapeo = Mapeo.search([('rule_code', '=', rule_code), ('area', '=', area)], limit=1)
                if not mapeo or not mapeo.account_debit_id or not mapeo.account_credit_id:
                    continue
                deb = ajuste if ajuste > 0 else 0.0
                cred = -ajuste if ajuste < 0 else 0.0
                lineas.append((0, 0, {
                    'account_id': mapeo.account_debit_id.id,
                    'name': 'Ajuste %s - %s' % (nombre, emp.name),
                    'debit': deb, 'credit': cred,
                    'analytic_distribution': distrib,
                }))
                lineas.append((0, 0, {
                    'account_id': mapeo.account_credit_id.id,
                    'name': 'Ajuste %s - %s' % (nombre, emp.name),
                    'debit': cred, 'credit': deb,
                }))
            if lineas:
                mv = Move.create({
                    'journal_id': self.journal_id.id,
                    'date': self.fecha_corte,
                    'ref': 'Ajuste provisiones %s - %s' % (self.fecha_corte, emp.name),
                    'line_ids': lineas,
                })
                moves |= mv
        if not moves:
            raise UserError(_("No hay ajustes que contabilizar (o falta el mapeo de cuentas)."))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'account.move',
            'view_mode': 'list,form', 'domain': [('id', 'in', moves.ids)],
            'name': _('Asientos de ajuste de provisiones'), 'target': 'current',
        }

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
