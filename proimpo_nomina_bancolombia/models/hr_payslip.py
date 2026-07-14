# -*- coding: utf-8 -*-
import re
import base64
from odoo import models, _
from odoo.exceptions import UserError



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


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    @staticmethod
    def _bc_solo_digitos(valor):
        return re.sub(r'\D', '', valor or '')

    def _bc_neto(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.salary_rule_id.code == 'NET')
        return int(round(sum(lines.mapped('total'))))

    def action_generar_bancolombia(self):
        """Genera el archivo plano de pago de nómina para Bancolombia con los recibos
        seleccionados. Devuelve la descarga del .txt."""
        ICP = self.env['ir.config_parameter'].sudo()
        convenio = ICP.get_param('proimpo_banco.convenio', '0056000780000')
        cola = ICP.get_param('proimpo_banco.cola', '06531979002D')
        desc = ICP.get_param('proimpo_banco.desc', 'PAGO NOMIN')
        tipo_pago = ICP.get_param('proimpo_banco.tipo_pago', '225')
        concepto = ICP.get_param('proimpo_banco.concepto', 'PAGNOMINA')

        slips = self.filtered(lambda s: s.state in ('done', 'paid')) or self
        slips = slips.filtered(lambda s: _es_empleado_propio(s.employee_id))
        if not slips:
            raise UserError(_("No hay recibos válidos seleccionados."))

        fecha_dt = max(s.date_to for s in slips if s.date_to)
        fecha = fecha_dt.strftime('%y%m%d')
        company = slips[0].company_id

        nit = self._bc_solo_digitos(company.vat)
        if len(nit) == 10:          # NIT + dígito de verificación -> quitar DV
            nit = nit[:9]

        detalles = []
        total = 0
        omitidos = []
        for s in slips:
            emp = s.employee_id
            ced = self._bc_solo_digitos(emp.identification_id)
            bank = emp.bank_account_id
            cta = self._bc_solo_digitos(bank.acc_number) if bank else ''
            neto = s._bc_neto()
            if not ced or not cta or neto <= 0:
                omitidos.append(emp.name)
                continue
            tipo = '2' if (bank.proimpo_tipo_cuenta == 'corriente') else '3'
            nombre = (emp.name or '').upper().ljust(18)[:18]
            detalles.append(
                "6" + ced.zfill(15) + nombre + convenio + cta.zfill(13)
                + "S" + tipo + "700" + str(neto).zfill(8)
                + concepto + fecha + " " * 7)
            total += neto

        if not detalles:
            raise UserError(_("Ningún recibo tenía cédula, cuenta y neto válidos."))

        header = ("1" + nit.zfill(10) + (company.name or '').upper().ljust(16)[:16]
                  + tipo_pago + desc + fecha + "A" + fecha
                  + str(len(detalles)).zfill(6) + str(total).zfill(24) + cola)

        contenido = "\r\n".join([header] + detalles) + "\r\n"
        att = self.env['ir.attachment'].create({
            'name': 'Bancolombia_%s.txt' % fecha,
            'type': 'binary',
            'datas': base64.b64encode(contenido.encode('latin-1')),
            'mimetype': 'text/plain',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % att.id,
            'target': 'self',
        }
