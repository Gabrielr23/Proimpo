# -*- coding: utf-8 -*-
import base64
import calendar
from odoo import models, _


# Categorías earn (Jorels) que Jorels cuantifica en DÍAS (ausencias que reemplazan laborados)
_CAT_DIAS = {
    'vacation_common',
    'licensings_maternity_or_paternity_leaves',
    'licensings_permit_or_paid_licenses',
    'licensings_suspension_or_unpaid_leaves',
    'incapacities_common', 'incapacities_professional', 'incapacities_working',
    'legal_strikes',
}
# Categorías earn que Jorels cuantifica en HORAS (horas extra y recargos)
_CAT_HORAS = {
    'daily_overtime', 'overtime_night_hours', 'hours_night_surcharge',
    'sunday_holiday_daily_overtime', 'daily_surcharge_hours_sundays_holidays',
    'sunday_night_overtime_holidays', 'sunday_holidays_night_surcharge_hours',
}


def _dias360(d1, d2):
    """Días del período con base 30 (una quincena normal = 15). Trata el último día del
    mes como 30, para que febrero (y meses de 31) paguen la quincena completa (15)."""
    if not d1 or not d2 or d2 < d1:
        return 0
    a1 = min(d1.day, 30)
    ultimo = calendar.monthrange(d2.year, d2.month)[1]
    a2 = 30 if d2.day == ultimo else min(d2.day, 30)
    return (d2.year - d1.year) * 360 + (d2.month - d1.month) * 30 + (a2 - a1) + 1


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    _TIPO_COD = {'libranza': 'LIBR', 'prestamo': 'PREST', 'otro': 'OTRO'}

    def _volante_prestamos(self):
        """Detalle de cuotas de prestamo/libranza del recibo, para desglosar en el
        volante. Usa las cuotas registradas (loan.line); si el recibo aun no las tiene
        (borrador), las calcula en vivo desde los prestamos activos del empleado."""
        self.ensure_one()
        if 'hr.employee.loan.line' not in self.env:
            return []
        res = []

        def add(loan, amount):
            res.append({
                'code': self._TIPO_COD.get(loan.loan_type, 'DESC'),
                'name': loan.name or 'Descuento',
                'amount': amount,
            })

        lines = self.env['hr.employee.loan.line'].search([('payslip_id', '=', self.id)])
        if lines:
            for l in lines.sorted(lambda x: (x.loan_id.loan_type or '', x.loan_id.name or '')):
                add(l.loan_id, l.amount)
        else:
            activos = self.employee_id.loan_ids.filtered(lambda x: x.state == 'open')
            for loan in activos.sorted(lambda x: (x.loan_type or '', x.name or '')):
                cuota = loan.get_installment_for_date(self.date_to)
                if cuota and cuota > 0:
                    add(loan, cuota)
        return res

    @staticmethod
    def _fmt_cant(qty):
        """Cantidad como texto: entero si es día completo, 2 decimales si son horas."""
        if not qty:
            return ''
        return ('%d' % qty) if float(qty).is_integer() else ('%.2f' % qty)

    # Horas por dia para el control del volante (convencion 210 h/mes = 7 h/dia, como CGUNO)
    _HORAS_DIA = 7.0
    # Conceptos que se cuantifican en DIAS en el recibo (cantidad de la linea = dias)
    _COD_DIAS = {'VAC', 'VACDISF', 'VACCOMP', 'LICR', 'LICMP', 'INCEG_EMP', 'INCEG_EPS', 'INCAT',
                 'LIQVAC'}
    # Conceptos en HORAS (cantidad de la linea = horas)
    _COD_HORAS = {'HED', 'HEN', 'HRN', 'HEDDF', 'HRDDF', 'HENDF', 'HRNDF', 'LICRH'}
    # Conceptos que suman a las HORAS BASE del periodo (tiempo laboral y ausencias pagadas);
    # las horas extra y recargos NO suman (igual que en CGUNO).
    _COD_BASE = {'BASIC', 'APOYO', 'VAC', 'VACDISF', 'LICR', 'LICRH', 'LICMP',
                 'INCEG_EMP', 'INCEG_EPS', 'INCAT'}

    def _volante_horas_periodo(self):
        """Horas base del periodo: dias (base 30) x 7 h. Una quincena = 105 h."""
        return _dias360(self.date_from, self.date_to) * self._HORAS_DIA

    def _volante_devengados(self):
        """Filas de devengados para el volante con la cantidad en HORAS (control de las
        105 h quincenales, como CGUNO):
        - Salario basico / apoyo -> horas = valor / (salario / 210).
        - Vacaciones, licencias, incapacidades -> dias de la linea x 7 h.
        - Horas extra, recargos y permisos por horas -> horas de la linea.
        - BONNS con varias entradas se desglosa por descripcion (earn.line.name).
        Devuelve (filas, horas_base)."""
        self.ensure_one()
        DESGLOSAR = {'BONNS'}
        wage = self.contract_id.wage or 0.0
        valor_hora = wage / 210.0 if wage else 0.0

        filas = []
        horas_base = 0.0
        devs = self.line_ids.filtered(
            lambda l: l.salary_rule_id.type_concept == 'earn' and l.total != 0)
        bonns_hecho = False
        for l in devs.sorted(lambda x: x.salary_rule_id.sequence):
            code = (l.salary_rule_id.code or '').upper()

            if code in DESGLOSAR:
                if bonns_hecho:
                    continue
                bonns_hecho = True
                bonns_lines = devs.filtered(lambda x: x.salary_rule_id.code in DESGLOSAR)
                total_bonns = sum(bonns_lines.mapped('total'))
                earns = self.earn_ids.filtered(lambda e: e.code in DESGLOSAR and e.total)
                suma = sum(earns.mapped('total'))
                if earns and abs(suma - total_bonns) < 1.0:
                    for e in earns.sorted(lambda x: x.sequence):
                        filas.append({'code': e.code or code, 'name': e.name or l.name,
                                      'qty_txt': '', 'amount': e.total})
                else:
                    for bl in bonns_lines.sorted(lambda x: x.salary_rule_id.sequence):
                        filas.append({'code': bl.salary_rule_id.code, 'name': bl.name,
                                      'qty_txt': '', 'amount': bl.total})
                continue

            horas = None
            if code == 'BASIC' and valor_hora:
                horas = l.total / valor_hora
            elif code == 'APOYO':
                apoyo_hora = (self.contract_id.company_id.smmlv_value or 0.0) * 0.75 / 210.0
                horas = l.total / apoyo_hora if apoyo_hora else None
            elif code in self._COD_DIAS:
                horas = (l.quantity or 0.0) * self._HORAS_DIA
            elif code in self._COD_HORAS:
                horas = l.quantity or 0.0
            if horas is not None and code in self._COD_BASE:
                horas_base += horas
            filas.append({'code': code, 'name': l.name,
                          'qty_txt': self._fmt_cant(horas) if horas is not None else '',
                          'amount': l.total})
        # v1.4.1: ausencias NO remuneradas como lineas informativas (sin valor), con sus
        # horas, para que el control de horas base cierre en 105 h (como CGUNO muestra
        # "Permiso parcial no remunerado").
        for wd in self.worked_days_line_ids:
            if wd.is_paid or not wd.work_entry_type_id:
                continue
            code = (wd.work_entry_type_id.code or '').upper()
            if code in ('LEAVE1200', 'LEAVE1000', 'LEAVE1100'):
                continue  # incapacidades/maternidad ya salen como concepto pagado
            horas = wd.number_of_hours or 0.0
            if not horas and wd.number_of_days:
                horas = wd.number_of_days * self._HORAS_DIA
            if not horas:
                continue
            horas_base += horas
            filas.append({'code': code, 'name': '%s (no remunerado)' % (wd.name or wd.work_entry_type_id.name),
                          'qty_txt': self._fmt_cant(round(horas, 2)), 'amount': 0.0, 'info': True})
        return filas, round(horas_base, 2)

    def _volante_email(self):
        self.ensure_one()
        emp = self.employee_id
        return emp.private_email or emp.work_email or False

    def action_enviar_volante(self):
        """Genera el volante en PDF y lo envía por correo al empleado.
        Funciona con uno o varios recibos (envío individual o masivo)."""
        template = self.env.ref('proimpo_nomina_volante.mail_template_volante', raise_if_not_found=False)
        enviados = 0
        sin_correo = []
        for slip in self:
            email = slip._volante_email()
            if not email:
                sin_correo.append(slip.employee_id.name)
                continue
            pdf, _ct = self.env['ir.actions.report']._render_qweb_pdf(
                'proimpo_nomina_volante.report_volante_document', slip.ids)
            att = self.env['ir.attachment'].create({
                'name': 'Volante_%s.pdf' % (slip.number or slip.id),
                'type': 'binary',
                'datas': base64.b64encode(pdf),
                'res_model': 'hr.payslip',
                'res_id': slip.id,
                'mimetype': 'application/pdf',
            })
            if template:
                template.send_mail(slip.id, force_send=True, email_values={
                    'email_to': email,
                    'attachment_ids': [(6, 0, [att.id])],
                })
            enviados += 1
        msg = _("Volantes enviados: %s") % enviados
        if sin_correo:
            msg += _(". Sin correo (no enviados): %s") % ", ".join(sin_correo)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Envío de volantes"),
                'message': msg,
                'type': 'success' if enviados else 'warning',
                'sticky': False,
            },
        }
