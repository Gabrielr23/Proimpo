# -*- coding: utf-8 -*-
import base64
from odoo import models, _


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
