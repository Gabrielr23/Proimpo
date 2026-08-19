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

    def _volante_devengados(self):
        """Filas de devengados para el volante con la cantidad poblada:
        - Salario básico -> días laborados (días del período menos ausencias en días).
        - Vacaciones / licencias / incapacidades -> días.
        - Horas extra y recargos -> horas.
        - BONNS con varias entradas se desglosa por descripción (earn.line.name)."""
        self.ensure_one()
        DESGLOSAR = {'BONNS'}

        dias_base = _dias360(self.date_from, self.date_to)
        dias_ausencia = sum(e.quantity for e in self.earn_ids
                            if e.category in _CAT_DIAS)

        def cantidad(code):
            earns = self.earn_ids.filtered(
                lambda e: e.code == code and e.category in (_CAT_DIAS | _CAT_HORAS))
            return sum(earns.mapped('quantity')) if earns else 0.0

        filas = []
        devs = self.line_ids.filtered(
            lambda l: l.salary_rule_id.type_concept == 'earn' and l.total != 0)
        for l in devs.sorted(lambda x: x.salary_rule_id.sequence):
            code = l.salary_rule_id.code
            if code == 'BASIC':
                qty = max(dias_base - dias_ausencia, 0.0)
            else:
                qty = cantidad(code)

            earns_total = self.earn_ids.filtered(lambda e: e.code == code and e.total)
            suma = sum(earns_total.mapped('total'))
            if code in DESGLOSAR and len(earns_total) > 1 and abs(suma - l.total) < 1.0:
                for e in earns_total.sorted(lambda x: x.sequence):
                    filas.append({'code': code, 'name': e.name or l.name,
                                  'qty_txt': '', 'amount': e.total})
            else:
                filas.append({'code': code, 'name': l.name,
                              'qty_txt': self._fmt_cant(qty), 'amount': l.total})
        return filas

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
