# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Umbrales por defecto, sobreescribibles con parámetros de sistema.
PARAMS = {
    'dias_reparacion': ('mrp_mold_management.alerta_dias_reparacion', 15),
    'dias_maquila': ('mrp_mold_management.alerta_dias_maquila', 60),
    'meses_sin_uso': ('mrp_mold_management.alerta_meses_sin_uso', 12),
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

    def _crear_actividad(self, record, resumen, nota, user):
        """Crea una actividad si no hay ya una igual pendiente.

        Alertar una sola vez por situación es deliberado: una alerta que
        se repite todos los días deja de leerse a la semana.
        """
        if not user:
            return False
        Activity = self.env['mail.activity'].sudo()
        modelo = self.env['ir.model']._get(record._name)
        existe = Activity.search_count([
            ('res_model_id', '=', modelo.id),
            ('res_id', '=', record.id),
            ('summary', '=', resumen),
        ])
        if existe:
            return False
        return Activity.create({
            'res_model_id': modelo.id,
            'res_id': record.id,
            'summary': resumen,
            'note': nota,
            'user_id': user.id,
            'date_deadline': fields.Date.context_today(self),
        })

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
        self._alerta_fuera_demasiado_tiempo()
        self._alerta_fuera_sin_solicitud()
        self._alerta_llegada_vencida()

    def _alerta_fuera_demasiado_tiempo(self):
        """Molde fuera de su casa más días de los aceptables."""
        dias_rep = self._param('dias_reparacion')
        dias_maq = self._param('dias_maquila')
        molds = self.env['maintenance.equipment'].sudo().search([
            ('is_mold', '=', True),
            ('is_away_from_home', '=', True),
        ])
        n = 0
        for mold in molds:
            if mold.mold_situation == 'baja':
                continue
            umbral = (dias_rep if mold.mold_situation == 'reparacion'
                      else dias_maq)
            if mold.days_away <= umbral:
                continue
            if self._crear_actividad(
                    mold,
                    'Molde fuera hace %s días' % mold.days_away,
                    'El molde lleva %s días fuera de su casa (%s). '
                    'El umbral configurado es %s días.'
                    % (mold.days_away, mold.location_display or 'sin ubicar',
                       umbral),
                    self._responsable(mold)):
                n += 1
        _logger.info('Alertas "fuera demasiado tiempo": %s creadas.', n)

    def _alerta_fuera_sin_solicitud(self):
        """El caso más peligroso: está fuera y nadie lo está siguiendo.

        Un molde en un taller sin solicitud de mantenimiento abierta no
        aparece en ninguna bandeja. Hoy eso solo se descubre cuando a
        alguien le hace falta.
        """
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
                    self._responsable(mold)):
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
                    self._responsable(mold)):
                n += 1
        _logger.info('Alertas "llegada vencida": %s creadas.', n)
