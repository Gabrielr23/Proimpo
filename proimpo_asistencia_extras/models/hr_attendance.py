# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta, time
import pytz
from odoo import models, api, fields

_logger = logging.getLogger(__name__)

# Campos de horas extra del modulo hr_att_expected
# Horas extra REALES (requieren aprobacion del gerente). Los recargos (HRN, HRDDF,
# HRNDF) son automaticos y NO requieren aprobacion.
COD_EXTRA_APROB = ['hed', 'hen', 'heddf', 'hendf']

# Recargos: son de LEY (C.S.T. art. 168 y ss.). Se pagan siempre que se trabajo
# de noche/festivo, esten o no autorizados. NUNCA pasan por aprobacion.
COD_RECARGO = ['hrn', 'hrddf', 'hrndf']

# Todos los conceptos que se pagan (extras + recargos).
COD_PAGO = COD_EXTRA_APROB + COD_RECARGO

COD_EXTRAS = [
    ('hed', 'Extra diurna'),
    ('hen', 'Extra nocturna'),
    ('hrn', 'Recargo nocturno'),
    ('heddf', 'Extra diurna dom/fest'),
    ('hrddf', 'Recargo diurno dom/fest'),
    ('hendf', 'Extra nocturna dom/fest'),
    ('hrndf', 'Recargo nocturno dom/fest'),
]

# Estados de aprobacion por concepto (solo para las horas extra reales).
SEL_ESTADO = [
    ('por_aprobar', 'Por aprobar'),
    ('aprobada', 'Aprobada'),
    ('rechazada', 'Rechazada'),
]


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    def _pa_autoaprobar(self):
        """Aprueba en tiempo real los registros completos sin horas extra reales
        (solo recargos o nada). Esos no requieren aprobacion del gerente."""
        if 'overtime_status' not in self._fields:
            return
        for r in self:
            if r.check_out and r.overtime_status == 'to_approve' and r._extras_reales() <= 0:
                r.with_context(pa_auto=True).write({'overtime_status': 'approved'})

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        if not self.env.context.get('pa_auto'):
            recs._pa_autoaprobar()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('pa_auto'):
            if any(k in vals for k in ('check_in', 'check_out')):
                self._pa_autoaprobar()
            if any(k.startswith('pa_estado_') for k in vals):
                self._pa_sync_overtime()
        return res

    pa_para_aprobar_por_mi = fields.Boolean(
        compute='_compute_pa_para_aprobar_por_mi',
        search='_search_pa_para_aprobar_por_mi',
        help="Tecnico: filtra las asistencias que le corresponde aprobar al usuario actual "
             "(su gerencia y areas debajo). RRHH/admin ven todas.")

    def _compute_pa_para_aprobar_por_mi(self):
        for r in self:
            r.pa_para_aprobar_por_mi = False

    @api.model
    def _search_pa_para_aprobar_por_mi(self, operator, value):
        user = self.env.user
        # RRHH / administradores ven todo
        if user.has_group('base.group_system') or \
           user.has_group('proimpo_asistencia_extras.group_asistencia_ver_todo'):
            return []
        emp = user.employee_id
        if not emp:
            return [('id', '=', 0)]
        # Departamentos que gestiona el usuario (es su gerente) + areas debajo
        gestiona = self.env['hr.department'].search([('manager_id', '=', emp.id)])
        if not gestiona:
            return [('id', '=', 0)]
        deptos = self.env['hr.department'].search([('id', 'child_of', gestiona.ids)])
        return [('employee_id.department_id', 'in', deptos.ids)]

    # ------------------------------------------------------------------
    # Aprobacion POR CONCEPTO
    # ------------------------------------------------------------------
    # Estado de cada hora extra real (los recargos no tienen estado: se pagan
    # siempre). Son campos calculados-almacenados y editables: el gerente puede
    # sobrescribir el valor por defecto (por_aprobar) con Aprobada/Rechazada.
    pa_estado_hed = fields.Selection(
        SEL_ESTADO, string="Estado HED", compute='_compute_pa_estados',
        store=True, readonly=False)
    pa_estado_hen = fields.Selection(
        SEL_ESTADO, string="Estado HEN", compute='_compute_pa_estados',
        store=True, readonly=False)
    pa_estado_heddf = fields.Selection(
        SEL_ESTADO, string="Estado HEDDF", compute='_compute_pa_estados',
        store=True, readonly=False)
    pa_estado_hendf = fields.Selection(
        SEL_ESTADO, string="Estado HENDF", compute='_compute_pa_estados',
        store=True, readonly=False)

    # Horas que efectivamente se pagan (lo unico que debe bajar al plano CGUNO).
    pa_hed_pagar = fields.Float(string="HED a pagar", compute='_compute_pa_pagar', store=True)
    pa_hen_pagar = fields.Float(string="HEN a pagar", compute='_compute_pa_pagar', store=True)
    pa_heddf_pagar = fields.Float(string="HEDDF a pagar", compute='_compute_pa_pagar', store=True)
    pa_hendf_pagar = fields.Float(string="HENDF a pagar", compute='_compute_pa_pagar', store=True)
    pa_hrn_pagar = fields.Float(string="RN a pagar", compute='_compute_pa_pagar', store=True)
    pa_hrddf_pagar = fields.Float(string="RDDF a pagar", compute='_compute_pa_pagar', store=True)
    pa_hrndf_pagar = fields.Float(string="RNDF a pagar", compute='_compute_pa_pagar', store=True)
    pa_total_pagar = fields.Float(string="Total a pagar (h)", compute='_compute_pa_pagar', store=True)

    @api.depends('hed', 'hen', 'heddf', 'hendf')
    def _compute_pa_estados(self):
        """Inicializa el estado de cada extra a 'por_aprobar' cuando tiene horas,
        y lo deja vacio cuando no. Respeta la decision manual del gerente
        (aprobada/rechazada) una vez tomada."""
        for r in self:
            for cod in COD_EXTRA_APROB:
                f = 'pa_estado_' + cod
                horas = getattr(r, cod, 0.0) or 0.0
                cur = r[f]
                if horas <= 0:
                    r[f] = False
                elif cur in ('aprobada', 'rechazada', 'por_aprobar'):
                    r[f] = cur
                else:
                    r[f] = 'por_aprobar'

    @api.depends('hed', 'hen', 'heddf', 'hendf', 'hrn', 'hrddf', 'hrndf',
                 'pa_estado_hed', 'pa_estado_hen', 'pa_estado_heddf', 'pa_estado_hendf')
    def _compute_pa_pagar(self):
        """Horas a pagar por concepto: el extra solo si esta 'aprobada'; el
        recargo siempre (es de ley)."""
        for r in self:
            total = 0.0
            for cod in COD_EXTRA_APROB:
                horas = getattr(r, cod, 0.0) or 0.0
                val = horas if r['pa_estado_' + cod] == 'aprobada' else 0.0
                r['pa_%s_pagar' % cod] = val
                total += val
            for cod in COD_RECARGO:
                horas = getattr(r, cod, 0.0) or 0.0
                r['pa_%s_pagar' % cod] = horas
                total += horas
            r.pa_total_pagar = total

    def _pa_sync_overtime(self):
        """Consolida el overtime_status nativo a partir de los estados por
        concepto: 'to_approve' mientras quede algun extra por decidir;
        'approved' (revisado) cuando ya se decidieron todos. Los recargos no
        influyen. Los registros sin extras los maneja _pa_autoaprobar."""
        if 'overtime_status' not in self._fields:
            return
        for r in self:
            estados = [r['pa_estado_' + c] for c in COD_EXTRA_APROB
                       if (getattr(r, c, 0.0) or 0.0) > 0]
            if not estados:
                continue
            nuevo = 'to_approve' if any(e in (False, 'por_aprobar') for e in estados) else 'approved'
            if r.overtime_status != nuevo:
                r.with_context(pa_auto=True).write({'overtime_status': nuevo})

    def _pa_set_estado_todos(self, estado):
        """Fija el mismo estado a todos los conceptos extra con horas del registro."""
        for r in self:
            vals = {}
            for cod in COD_EXTRA_APROB:
                if (getattr(r, cod, 0.0) or 0.0) > 0:
                    vals['pa_estado_' + cod] = estado
            if vals:
                r.write(vals)
        self._pa_sync_overtime()

    def _pa_notif(self, msg, tipo='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': "Horas extra", 'message': msg,
                       'type': tipo, 'sticky': False},
        }

    def action_pa_aprobar_todo(self):
        """Boton: aprueba TODAS las horas extra del registro."""
        self._pa_set_estado_todos('aprobada')
        return self._pa_notif("Horas extra aprobadas: %d registro(s)." % len(self))

    def action_pa_rechazar_todo(self):
        """Boton / accion masiva: rechaza TODAS las horas extra de los registros
        seleccionados (los recargos se siguen pagando)."""
        self._pa_set_estado_todos('rechazada')
        return self._pa_notif("Horas extra rechazadas: %d registro(s)." % len(self))

    def action_pa_aprobar_pendientes(self):
        """Aprobacion MASIVA: aprueba solo los conceptos que siguen 'por_aprobar'
        y RESPETA lo ya rechazado o aprobado. Pensado para el flujo de muchos
        empleados: el gerente rechaza lo puntual y luego, sobre la seleccion (o
        seleccionando todo), aprueba en bloque todo lo demas."""
        n = 0
        for r in self:
            vals = {}
            for cod in COD_EXTRA_APROB:
                if (getattr(r, cod, 0.0) or 0.0) > 0 and r['pa_estado_' + cod] == 'por_aprobar':
                    vals['pa_estado_' + cod] = 'aprobada'
            if vals:
                r.write(vals)
                n += 1
        self._pa_sync_overtime()
        return self._pa_notif("Aprobación masiva: %d registro(s) con horas pendientes aprobadas. "
                              "Los rechazos se conservaron." % n)

    def _extras_total(self):
        """Suma de todas las horas extra/recargos del registro."""
        self.ensure_one()
        return sum((getattr(self, f, 0.0) or 0.0) for f, _n in COD_EXTRAS)

    def _extras_reales(self):
        """Suma de horas extra REALES (HED, HEN, HEDDF, HENDF) que requieren aprobacion."""
        self.ensure_one()
        return sum((getattr(self, f, 0.0) or 0.0) for f in COD_EXTRA_APROB)

    @api.model
    def _extras_autoaprobar_sin_extra(self, dia):
        """Aprueba automaticamente los registros del dia sin horas extra reales
        (solo recargos o nada); esos no requieren aprobacion del gerente."""
        if 'overtime_status' not in self._fields:
            return 0
        from datetime import datetime, time
        ini = datetime.combine(dia, time.min)
        fin = datetime.combine(dia, time.max)
        regs = self.search([('check_in', '>=', ini), ('check_in', '<=', fin),
                            ('overtime_status', '=', 'to_approve')])
        sin_extra = regs.filtered(lambda r: r._extras_reales() <= 0)
        if sin_extra:
            sin_extra.write({'overtime_status': 'approved'})
        return len(sin_extra)

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
        return regs.filtered(lambda r: r._extras_reales() > 0)

    @api.model
    @api.model
    def _pa_hora_local(self, empleado, dt):
        """Devuelve HH:MM del datetime (UTC) en la zona del empleado (o Colombia)."""
        if not dt:
            return ''
        tz_name = (empleado.resource_calendar_id.tz if empleado and empleado.resource_calendar_id else None) \
            or (empleado.tz if empleado else None) or 'America/Bogota'
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.timezone('America/Bogota')
        return pytz.UTC.localize(dt).astimezone(tz).strftime('%H:%M')

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
                    self._pa_hora_local(r.employee_id, r.check_in),
                    self._pa_hora_local(r.employee_id, r.check_out),
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
        # Aprobar automaticamente los registros sin horas extra reales (solo recargos o nada)
        self._extras_autoaprobar_sin_extra(dia)
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
