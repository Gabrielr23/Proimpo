# -*- coding: utf-8 -*-
import base64
from odoo import models, _


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

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
