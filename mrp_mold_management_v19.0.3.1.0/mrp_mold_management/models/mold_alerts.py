# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Umbrales por defecto, sobreescribibles desde Moldes → Configuración de
# Alertas (o con parámetros de sistema).
PARAMS = {
    'dias_reparacion': ('mrp_mold_management.alerta_dias_reparacion', 15),
    'dias_escalamiento': ('mrp_mold_management.alerta_dias_escalamiento', 30),
    'dias_maquila': ('mrp_mold_management.alerta_dias_maquila', 60),
    'dias_externo': ('mrp_mold_management.alerta_dias_externo', 30),
}
USER_PARAMS = {
    'jefe': 'mrp_mold_management.alerta_jefe_mantenimiento_id',
    'superior': 'mrp_mold_management.alerta_jefe_superior_id',
    'externo': 'mrp_mold_management.alerta_responsable_externo_id',
}


class MrpMoldAlerts(models.AbstractModel):
    _name = 'mrp.mold.alerts'
    _description = ('Alertas de moldes. Sin tabla propia: agrupa la lógica '
                    'que ejecutan las acciones planificadas.')

    @api.model
    def _param(self, clave):
        nombre, defecto = PARAMS[clave]
        valor = self.env['ir.config_parameter'].sudo().get_param(nombre)
        try:
            return int(valor) if valor else defecto
        except (TypeError, ValueError):
            _logger.warning('Parámetro %s no es un número: %r. Se usa %s.',
                            nombre, valor, defecto)
            return defecto

    @api.model
    def _configured_user(self, clave):
        """Usuario configurado en Moldes → Configuración de Alertas."""
        valor = self.env['ir.config_parameter'].sudo().get_param(
            USER_PARAMS[clave])
        if valor and str(valor).isdigit():
            user = self.env['res.users'].sudo().browse(int(valor)).exists()
            if user and user.active:
                return user
        return self.env['res.users']

    def _crear_actividad(self, record, resumen, nota, user, key=None):
        """Crea una actividad una sola vez por situación.

        Si el registro lleva `alert_flags` (moldes) y se pasa `key`, la
        marca queda guardada ahí: así NO se repite aunque la persona ya haya
        cerrado la actividad. La marca se borra cuando la situación termina
        (el molde vuelve a su ubicación). Para otros registros se evita el
        duplicado buscando una actividad pendiente con el mismo resumen.
        """
        if not user:
            return False
        usa_marca = bool(key) and 'alert_flags' in record._fields
        if usa_marca:
            if key in (record.alert_flags or '').split(','):
                return False
        else:
            modelo = self.env['ir.model']._get(record._name)
            if self.env['mail.activity'].sudo().search_count([
                    ('res_model_id', '=', modelo.id),
                    ('res_id', '=', record.id),
                    ('summary', '=', resumen)]):
                return False
        modelo = self.env['ir.model']._get(record._name)
        act = self.env['mail.activity'].sudo().create({
            'res_model_id': modelo.id,
            'res_id': record.id,
            'summary': resumen,
            'note': nota,
            'user_id': user.id,
            'date_deadline': fields.Date.context_today(self),
        })
        if usa_marca:
            flags = [f for f in (record.alert_flags or '').split(',') if f]
            record.sudo().write({'alert_flags': ','.join(flags + [key])})
        return act

    def _responsable(self, mold):
        return (mold.technician_user_id
                or mold.owner_user_id
                or mold.maintenance_team_id.member_ids[:1].mapped('id')
                and self.env['res.users'].browse(
                    mold.maintenance_team_id.member_ids[0].id)
                or self.env.user)

    # ------------------------------------------------------------------
    @api.model
    def _cron_alertas_moldes(self):
        self._limpiar_marcas()
        self._alerta_fuera_demasiado_tiempo()
        self._alerta_fuera_sin_solicitud()
        self._alerta_llegada_vencida()

    def _limpiar_marcas(self):
        """Cuando un molde vuelve a su ubicación, sus alertas de "fuera"
        quedan libres para una próxima salida."""
        Eq = self.env['maintenance.equipment'].sudo()
        for mold in Eq.search([('alert_flags', '!=', False),
                               ('is_away_from_home', '=', False)]):
            quedan = [f for f in mold.alert_flags.split(',')
                      if f == 'llegada']
            mold.write({'alert_flags': ','.join(quedan) or False})

    def _alerta_fuera_demasiado_tiempo(self):
        """Molde fuera de su ubicación más días de los aceptables.

        En REPARACIÓN hay dos niveles: a los N días avisa al jefe de
        mantenimiento y a los M días escala a un jefe superior. Si el molde
        está en un PROVEEDOR EXTERNO produciendo, hay un aviso propio con
        su umbral y su destinatario. En otras salidas hay un solo aviso, al
        jefe de mantenimiento. Los destinatarios se configuran en Moldes →
        Configuración de Alertas; sin configurar, se usa el responsable
        del molde.
        """
        dias_rep = self._param('dias_reparacion')
        dias_esc = self._param('dias_escalamiento')
        dias_maq = self._param('dias_maquila')
        dias_ext = self._param('dias_externo')
        jefe = self._configured_user('jefe')
        superior = self._configured_user('superior')
        resp_ext = self._configured_user('externo') or jefe
        molds = self.env['maintenance.equipment'].sudo().search([
            ('is_mold', '=', True),
            ('is_away_from_home', '=', True),
        ])
        n = 0
        for mold in molds:
            if mold.mold_situation == 'baja':
                continue
            ubic = mold.location_display or 'sin ubicar'
            dias = mold.days_away
            if mold.mold_situation == 'reparacion':
                if dias > dias_rep and self._crear_actividad(
                        mold,
                        'Molde en reparación hace más de %s días' % dias_rep,
                        'El molde lleva %s días en reparación (%s). El '
                        'primer aviso está configurado a los %s días.'
                        % (dias, ubic, dias_rep),
                        jefe or self._responsable(mold), key='rep1'):
                    n += 1
                if dias > dias_esc and superior and self._crear_actividad(
                        mold,
                        'ESCALAMIENTO: molde en reparación hace más de %s '
                        'días' % dias_esc,
                        'El molde lleva %s días en reparación (%s) y ya se '
                        'avisó a mantenimiento a los %s días. Requiere '
                        'una decisión.' % (dias, ubic, dias_rep),
                        superior, key='rep2'):
                    n += 1
            elif mold._external_production_workcenter():
                prov = mold._external_production_workcenter()
                if dias > dias_ext and self._crear_actividad(
                        mold,
                        'Molde en proveedor externo hace más de %s días'
                        % dias_ext,
                        'El molde lleva %s días en %s produciendo. El '
                        'umbral configurado es %s días: verifica con el '
                        'proveedor el avance y si todavía se necesita allá.'
                        % (dias, prov.display_name, dias_ext),
                        resp_ext or self._responsable(mold), key='ext'):
                    n += 1
            elif dias > dias_maq and self._crear_actividad(
                    mold,
                    'Molde fuera hace más de %s días' % dias_maq,
                    'El molde lleva %s días fuera de su ubicación de '
                    'almacenamiento (%s). El umbral configurado es %s días.'
                    % (dias, ubic, dias_maq),
                    jefe or self._responsable(mold), key='maq'):
                n += 1
        _logger.info('Alertas "fuera demasiado tiempo": %s creadas.', n)

    def _alerta_fuera_sin_solicitud(self):
        """El caso más peligroso: está fuera y nadie lo está siguiendo.

        Un molde en un taller sin solicitud de mantenimiento abierta no
        aparece en ninguna bandeja. Hoy eso solo se descubre cuando a
        alguien le hace falta.
        """
        jefe = self._configured_user('jefe')
        molds = self.env['maintenance.equipment'].sudo().search([
            ('is_mold', '=', True),
            ('is_away_from_home', '=', True),
            ('mold_situation', 'not in', ('produccion', 'reparacion', 'baja')),
        ])
        n = 0
        for mold in molds:
            if not mold.days_away:
                continue
            if self._crear_actividad(
                    mold,
                    'Molde fuera sin solicitud de mantenimiento',
                    'Está en %s desde hace %s días, sin orden de trabajo en '
                    'curso ni solicitud de mantenimiento abierta. Nadie lo '
                    'está siguiendo.'
                    % (mold.location_display or 'ubicación desconocida',
                       mold.days_away),
                    jefe or self._responsable(mold), key='sinsol'):
                n += 1
        _logger.info('Alertas "fuera sin solicitud": %s creadas.', n)

    def _alerta_llegada_vencida(self):
        """Comprado, pasó la fecha prevista y no ha llegado."""
        hoy = fields.Date.context_today(self)
        molds = self.env['maintenance.equipment'].sudo().search([
            ('is_mold', '=', True),
            ('arrival_date', '=', False),
            ('expected_arrival_date', '!=', False),
            ('expected_arrival_date', '<', hoy),
        ])
        n = 0
        for mold in molds:
            dias = (hoy - mold.expected_arrival_date).days
            if self._crear_actividad(
                    mold,
                    'Llegada de molde vencida',
                    'La llegada estaba prevista para el %s (%s días de '
                    'atraso) y aún no se registra la recepción.'
                    % (mold.expected_arrival_date, dias),
                    self._responsable(mold), key='llegada'):
                n += 1
        _logger.info('Alertas "llegada vencida": %s creadas.', n)
