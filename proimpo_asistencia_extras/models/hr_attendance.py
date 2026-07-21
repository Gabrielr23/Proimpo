# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta, time
from odoo import models, api, fields

_logger = logging.getLogger(__name__)

# Campos de horas extra del modulo hr_att_expected
COD_EXTRAS = [
    ('hed', 'Extra diurna'),
    ('hen', 'Extra nocturna'),
    ('hrn', 'Recargo nocturno'),
    ('heddf', 'Extra diurna dom/fest'),
    ('hrddf', 'Recargo diurno dom/fest'),
    ('hendf', 'Extra nocturna dom/fest'),
    ('hrndf', 'Recargo nocturno dom/fest'),
]


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    def _extras_total(self):
        """Suma de todas las horas extra/recargos del registro."""
        self.ensure_one()
        return sum((getattr(self, f, 0.0) or 0.0) for f, _n in COD_EXTRAS)

    @api.model
    def _extras_destinatarios(self):
        """Correos destinatarios del reporte (parametro del sistema, separados por coma)."""
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('proimpo_asistencia.destinatarios', '') or ''
        return [e.strip() for e in raw.replace(';', ',').split(',') if e.strip()]

    @api.model
    def _extras_buscar_pendientes(self, dia):
        """Registros del dia con horas extra y pendientes de aprobacion."""
        ini = datetime.combine(dia, time.min)
        fin = datetime.combine(dia, time.max)
        dom = [('check_in', '>=', ini), ('check_in', '<=', fin)]
        # Solo pendientes de aprobacion (campo nativo de Odoo), si existe
        if 'overtime_status' in self._fields:
            dom.append(('overtime_status', '=', 'to_approve'))
        # Incluye tambien a los temporales: su aprobacion tambien aplica.
        regs = self.search(dom, order='employee_id, check_in')
        return regs.filtered(lambda r: r._extras_total() > 0)

    @api.model
    def _extras_html(self, regs, dia, url, destinatario=None):
        """Arma el cuerpo HTML del correo."""
        def hhmm(v):
            v = v or 0.0
            h = int(v)
            m = int(round((v - h) * 60))
            if m == 60:
                h, m = h + 1, 0
            return "%d:%02d" % (h, m)

        cols = "".join("<th style='padding:6px 8px;border:1px solid #ccc;background:#1F4E79;"
                       "color:#fff;font-size:12px;'>%s</th>" % n for _f, n in COD_EXTRAS)
        filas = []
        tot = {f: 0.0 for f, _n in COD_EXTRAS}
        for r in regs:
            tds = ""
            for f, _n in COD_EXTRAS:
                v = getattr(r, f, 0.0) or 0.0
                tot[f] += v
                tds += ("<td style='padding:5px 8px;border:1px solid #ddd;text-align:center;"
                        "font-size:12px;%s'>%s</td>" % ("font-weight:bold;" if v else "color:#bbb;",
                                                        hhmm(v) if v else "-"))
            filas.append(
                "<tr>"
                "<td style='padding:5px 8px;border:1px solid #ddd;font-size:12px;'>%s</td>"
                "<td style='padding:5px 8px;border:1px solid #ddd;font-size:12px;text-align:center;'>%s</td>"
                "<td style='padding:5px 8px;border:1px solid #ddd;font-size:12px;text-align:center;'>%s</td>"
                "%s"
                "<td style='padding:5px 8px;border:1px solid #ddd;text-align:center;font-size:12px;"
                "font-weight:bold;background:#DDEBF7;'>%s</td></tr>" % (
                    r.employee_id.name or '',
                    fields.Datetime.context_timestamp(r, r.check_in).strftime('%H:%M') if r.check_in else '',
                    fields.Datetime.context_timestamp(r, r.check_out).strftime('%H:%M') if r.check_out else '',
                    tds, hhmm(r._extras_total())))
        tds_tot = "".join("<td style='padding:5px 8px;border:1px solid #ccc;text-align:center;"
                          "font-size:12px;font-weight:bold;'>%s</td>" % hhmm(tot[f]) for f, _n in COD_EXTRAS)
        gran = hhmm(sum(tot.values()))
        return """
<div style="font-family:Arial,sans-serif;color:#222;">
  <p style="font-size:15px;"><b>Horas extra pendientes de aprobación</b>%s</p>
  <p style="font-size:13px;">Registros del <b>%s</b> con horas extra que están <b>por aprobar</b>.
  Son <b>%d</b> registro(s), con un total de <b>%s</b> horas.</p>
  <table style="border-collapse:collapse;margin:12px 0;">
    <tr>
      <th style="padding:6px 8px;border:1px solid #ccc;background:#1F4E79;color:#fff;font-size:12px;">Empleado</th>
      <th style="padding:6px 8px;border:1px solid #ccc;background:#1F4E79;color:#fff;font-size:12px;">Entrada</th>
      <th style="padding:6px 8px;border:1px solid #ccc;background:#1F4E79;color:#fff;font-size:12px;">Salida</th>
      %s
      <th style="padding:6px 8px;border:1px solid #ccc;background:#1F4E79;color:#fff;font-size:12px;">Total</th>
    </tr>
    %s
    <tr style="background:#F2F2F2;">
      <td colspan="3" style="padding:5px 8px;border:1px solid #ccc;font-size:12px;font-weight:bold;">TOTALES</td>
      %s
      <td style="padding:5px 8px;border:1px solid #ccc;text-align:center;font-size:12px;font-weight:bold;background:#DDEBF7;">%s</td>
    </tr>
  </table>
  <p style="margin:18px 0;">
    <a href="%s" style="background:#1F4E79;color:#fff;padding:10px 18px;text-decoration:none;
       border-radius:4px;font-size:13px;font-weight:bold;">Revisar y aprobar en Odoo</a>
  </p>
  <p style="font-size:11px;color:#777;">Mensaje automático — PROIMPO SAS. Las horas se aprueban o rechazan
  en cada registro de asistencia.</p>
</div>""" % (" — %s" % destinatario if destinatario else "", dia.strftime('%d/%m/%Y'), len(regs), gran, cols, "".join(filas), tds_tot, gran, url)

    @api.model
    def _extras_enviar(self, email_to, asunto, cuerpo):
        self.env['mail.mail'].sudo().create({
            'subject': asunto, 'body_html': cuerpo,
            'email_to': email_to, 'auto_delete': False,
        }).send()

    @api.model
    def cron_reporte_extras_diario(self):
        """Envia el reporte de horas extra por aprobar del dia anterior.
        A cada GERENTE DE AREA le llegan solo las de su gerencia; Nomina/RRHH
        recibe el consolidado de todos."""
        dia = fields.Date.context_today(self) - timedelta(days=1)
        regs = self._extras_buscar_pendientes(dia)
        if not regs:
            _logger.info("PROIMPO extras: sin horas extra por aprobar del %s.", dia)
            return True
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        try:
            act = self.env.ref('proimpo_asistencia_extras.action_extras_por_aprobar')
            url = "%s/odoo/action-%s" % (base, act.id)
        except Exception:
            url = base

        # Agrupar por gerente de area (aprobador)
        grupos = {}
        sin_gerente = self.browse()
        for r in regs:
            ger = r.employee_id._pa_gerente_aprobador()
            correo = ger._pa_email() if ger else ''
            if ger and correo:
                g = grupos.setdefault(ger.id, {'ger': ger, 'mail': correo, 'regs': self.browse()})
                g['regs'] |= r
            else:
                sin_gerente |= r

        for g in grupos.values():
            self._extras_enviar(
                g['mail'],
                "Horas extra por aprobar - %s (%d registros)" % (dia.strftime('%d/%m/%Y'), len(g['regs'])),
                self._extras_html(g['regs'], dia, url, destinatario=g['ger'].name))

        # Consolidado a Nomina / RRHH
        dest = self._extras_destinatarios()
        if dest:
            nota = ""
            if sin_gerente:
                nombres = ", ".join(sorted(set(sin_gerente.mapped('employee_id.name'))))
                nota = ("<p style='font-size:12px;color:#C00000;'><b>Atención:</b> %d registro(s) no tienen "
                        "gerente de área asignado, así que no se enviaron a ningún aprobador: %s</p>"
                        % (len(sin_gerente), nombres))
            self._extras_enviar(
                ','.join(dest),
                "Consolidado horas extra por aprobar - %s (%d registros)" % (dia.strftime('%d/%m/%Y'), len(regs)),
                nota + self._extras_html(regs, dia, url, destinatario="Nómina / RRHH"))

        _logger.info("PROIMPO extras: %s — %d gerente(s), %d registro(s), %d sin gerente.",
                     dia, len(grupos), len(regs), len(sin_gerente))
        return True
