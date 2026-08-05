# -*- coding: utf-8 -*-
from datetime import date
from collections import defaultdict
from odoo import models, api


def _dias360(d1, d2):
    if not d1 or not d2 or d2 < d1:
        return 0
    a1 = min(d1.day, 30); a2 = min(d2.day, 30)
    return (d2.year - d1.year) * 360 + (d2.month - d1.month) * 30 + (a2 - a1) + 1


def _mil(v):
    """Aproxima al multiplo de mil (formato DIAN)."""
    return int(round((v or 0) / 1000.0)) * 1000


class Cert220Report(models.AbstractModel):
    _name = 'report.proimpo_nomina_certificado.cert220_document'
    _description = 'Certificado de ingresos y retenciones 220'

    def _cesantias_consignadas(self, emp, anio, smmlv, aux):
        ini = date(anio, 1, 1); fin = date(anio, 12, 31)
        total = 0.0
        for ct in emp.contract_ids:
            if ct.integral_salary or ct.state not in ('open', 'close'):
                continue
            if ct.date_start > fin or (ct.date_end and ct.date_end < ini):
                continue
            d1 = max(ct.date_start, ini); d2 = min(ct.date_end or fin, fin)
            dias = _dias360(d1, d2)
            base = ct.wage + (aux if ct.wage <= 2 * smmlv else 0)
            total += base * dias / 360.0
        return total

    @api.model
    def _casillas_empleado(self, emp, anio, smmlv, aux):
        ini = date(anio, 1, 1); fin = date(anio, 12, 31)
        slips = self.env['hr.payslip'].search([
            ('employee_id', '=', emp.id), ('state', 'in', ('done', 'paid')),
            ('date_from', '>=', ini), ('date_to', '<=', fin)])
        cas = defaultdict(float)
        for line in slips.mapped('line_ids'):
            k = line.salary_rule_id.cert220_casilla
            if not k:
                continue
            val = line.total
            if k in ('50', '51', '52', '53', '54', '55'):
                val = abs(val)
            cas[k] += val
        cas['47'] = self._cesantias_consignadas(emp, anio, smmlv, aux)
        cas['49'] = sum(cas.get(str(n), 0.0) for n in range(36, 49))
        cas['70'] = cas.get('55', 0.0)
        return {k: _mil(v) for k, v in cas.items()}

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        anio = int(data.get('anio') or (date.today().year - 1))
        smmlv = float(data.get('smmlv') or 0.0)
        aux = float(data.get('aux') or 0.0)
        emp_ids = data.get('emp_ids') or docids
        empleados = self.env['hr.employee'].browse(emp_ids).exists()
        company = self.env.company
        registros = []
        for e in empleados:
            registros.append({'emp': e, 'cas': self._casillas_empleado(e, anio, smmlv, aux)})
        return {
            'doc_ids': emp_ids, 'doc_model': 'hr.employee',
            'docs': empleados, 'anio': anio, 'company': company, 'registros': registros,
        }
