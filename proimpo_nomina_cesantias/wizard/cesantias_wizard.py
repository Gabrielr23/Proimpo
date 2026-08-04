# -*- coding: utf-8 -*-
import io
import base64
import calendar
from datetime import date
from odoo import models, fields, api, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


def _dias360(d1, d2):
    """Dias entre dos fechas en convencion comercial de 360 (meses de 30)."""
    if d2 < d1:
        return 0
    day1 = min(d1.day, 30)
    day2 = min(d2.day, 30)
    return (d2.year - d1.year) * 360 + (d2.month - d1.month) * 30 + (day2 - day1) + 1


def _split_nombre(nombre):
    nombre = (nombre or '').strip().upper()
    if ',' in nombre:
        ape, nom = nombre.split(',', 1)
    else:
        parts = nombre.split()
        ape = ' '.join(parts[:2]); nom = ' '.join(parts[2:])
    ape = ape.split(); nom = nom.split()
    return (ape[0] if ape else '', ' '.join(ape[1:]) if len(ape) > 1 else '',
            nom[0] if nom else '', ' '.join(nom[1:]) if len(nom) > 1 else '')



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


class CesantiasConsignacionWizard(models.TransientModel):
    _name = 'cesantias.consignacion.wizard'
    _description = 'Consignacion anual de cesantias'

    anio = fields.Integer(string="Ano a consignar", required=True,
                          default=lambda s: date.today().year - 1)
    smmlv = fields.Float(string="SMMLV del ano", required=True,
                         default=lambda s: s.env.company.smmlv_value or 0.0)
    aux_transporte = fields.Float(string="Auxilio de transporte del ano", required=True,
                                  default=1)
    incluir_transporte = fields.Boolean(
        string="Incluir auxilio de transporte en la base", default=True,
        help="Suma el auxilio de transporte a la base (cuando el salario no supera 2 SMMLV).")

    def _computar(self):
        """Devuelve lista de dicts por empleado con base, dias, cesantias, provision, fondo."""
        self.ensure_one()
        y = self.anio
        ini_ano = date(y, 1, 1)
        fin_ano = date(y, 12, 31)
        Contract = self.env['hr.contract']
        contratos = Contract.search([
            ('date_start', '<=', fin_ano),
            '|', ('date_end', '=', False), ('date_end', '>=', ini_ano),
            ('state', 'in', ('open', 'close')),
        ] + _dom_empresa_propia(self.env))
        res = []
        for ct in contratos:
            if ct.integral_salary:
                continue  # salario integral no causa cesantias
            emp = ct.employee_id
            if not ct.fondo_cesantias:
                res.append({'ct': ct, 'emp': emp, 'error': 'Sin fondo de cesantias'})
                continue
            # MOTOR UNICO: cesantias causadas del ano (incluye promedio de variables)
            corte = min(ct.date_end or fin_ano, fin_ano)
            aux = self.aux_transporte if self.incluir_transporte else 0.0
            p = ct._proimpo_prestaciones_causadas(corte, self.smmlv, aux)
            base = round(p['base_ces'])
            dias = p['dias_ano']
            ces = round(p['ces'])
            # provision acumulada (comparacion)
            slips = self.env['hr.payslip'].search([
                ('contract_id', '=', ct.id), ('state', 'in', ('done', 'paid')),
                ('date_from', '>=', ini_ano), ('date_to', '<=', fin_ano),
            ])
            prov = 0.0
            for s in slips:
                prov += sum(s.line_ids.filtered(
                    lambda l: l.salary_rule_id.code in ('PROVCES', 'PROVISIONCES')).mapped('total'))
            res.append({'ct': ct, 'emp': emp, 'base': base, 'dias': dias,
                        'cesantias': ces, 'provision': round(prov), 'fondo': ct.fondo_cesantias})
        return res

    def action_generar_plano(self):
        datos = [d for d in self._computar() if not d.get('error') and d['cesantias'] > 0]
        if not datos:
            raise UserError(_("No hay cesantias por consignar para el ano %s.") % self.anio)
        datos.sort(key=lambda d: (d['fondo'], d['emp'].identification_id or ''))
        lineas = []
        for d in datos:
            e = d['emp']
            ap1, ap2, no1, no2 = _split_nombre(e.name)
            campos = [
                'CC', (e.identification_id or '').strip(), ap1, ap2, no1, no2,
                d['fondo'], str(int(round(d['base']))).zfill(13),
                str(int(d['cesantias'])).zfill(13),
            ]
            lineas.append(','.join(campos).ljust(3000)[:3000])
        contenido = '\n'.join(lineas) + '\n'
        att = self.env['ir.attachment'].create({
            'name': 'APORTES_CESANTIAS_%s.TXT' % self.anio, 'type': 'binary',
            'datas': base64.b64encode(contenido.encode('latin-1')), 'mimetype': 'text/plain',
        })
        return {'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}

    def action_generar_reporte(self):
        if xlsxwriter is None:
            raise UserError(_("Falta la libreria xlsxwriter en el servidor."))
        datos = self._computar()
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Cesantias %s' % self.anio)
        navy = '#1F4E79'
        f_t = wb.add_format({'bold': True, 'font_size': 13, 'font_color': navy})
        f_h = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': navy, 'border': 1,
                             'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        f_x = wb.add_format({'border': 1, 'font_size': 9})
        f_n = wb.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 9})
        f_tot = wb.add_format({'border': 1, 'num_format': '#,##0', 'bold': True, 'bg_color': '#DDEBF7'})
        ws.write(0, 0, "Consignacion de cesantias %s (recalculo al 31 dic)" % self.anio, f_t)
        hdr = ['Cedula', 'Empleado', 'Fondo', 'Dias', 'Base', 'Cesantias (recalculo)',
               'Provision acumulada', 'Diferencia', 'Observacion']
        for c, h in enumerate(hdr):
            ws.write(2, c, h, f_h)
        r = 3
        tc = tp = 0
        for d in sorted(datos, key=lambda x: (x.get('fondo') or '', x['emp'].name or '')):
            e = d['emp']
            if d.get('error'):
                ws.write(r, 0, e.identification_id or '', f_x); ws.write(r, 1, e.name or '', f_x)
                ws.write(r, 8, d['error'], f_x); r += 1; continue
            dif = d['cesantias'] - d['provision']
            ws.write(r, 0, e.identification_id or '', f_x)
            ws.write(r, 1, e.name or '', f_x)
            ws.write(r, 2, d['fondo'], f_x)
            ws.write(r, 3, d['dias'], f_n)
            ws.write(r, 4, d['base'], f_n)
            ws.write(r, 5, d['cesantias'], f_n)
            ws.write(r, 6, d['provision'], f_n)
            ws.write(r, 7, dif, f_n)
            r += 1
            tc += d['cesantias']; tp += d['provision']
        ws.write(r, 1, 'TOTALES', f_tot)
        for c in (2, 3, 4): ws.write(r, c, '', f_tot)
        ws.write(r, 5, tc, f_tot); ws.write(r, 6, tp, f_tot); ws.write(r, 7, tc - tp, f_tot)
        ws.set_column(0, 0, 13); ws.set_column(1, 1, 32); ws.set_column(2, 2, 12)
        ws.set_column(3, 8, 15); ws.freeze_panes(3, 2)
        wb.close(); output.seek(0)
        att = self.env['ir.attachment'].create({
            'name': 'Reporte_Cesantias_%s.xlsx' % self.anio, 'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}
