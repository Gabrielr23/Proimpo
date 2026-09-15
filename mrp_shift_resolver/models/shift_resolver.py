# -*- coding: utf-8 -*-
import pytz

from odoo import api, models


class MrpShiftResolver(models.AbstractModel):
    _name = 'mrp.shift.resolver'
    _description = ('Resuelve a qué turno de producción pertenece una fecha/hora, '
                    'según el calendario del centro de trabajo. Sin tabla propia: '
                    'es lógica compartida que consumen mrp_oee_report, '
                    'mrp_oee_dashboard y mrp_production_alerts.')

    @api.model
    def resolve_shift(self, workcenter, dt):
        """Identifica el turno al que pertenece una fecha/hora real.

        :param workcenter: registro único de mrp.workcenter
        :param dt: datetime naive en UTC (como lo devuelve el ORM para
            campos Datetime, p. ej. mrp.workcenter.productivity.date_start)
        :return: dict con:
            - shift_name (str o False): nombre EXACTO de la línea de
              asistencia, p. ej. "Lunes Turno 3". False si no se encontró
              ninguna línea que cubra esa hora (hueco en el calendario, o
              el centro de trabajo no tiene calendario asignado).
            - is_planned (bool): False si la franja es day_period='lunch'
              (capacidad apagada por diseño — fin de semana, turno
              reducido). Nunca decide si la producción real se descarta,
              solo si el objetivo de esa franja es 0.
            - attendance: el registro de resource.calendar.attendance
              encontrado, o un recordset vacío.

        No compara el turno contra "el día de hoy": busca por el día real
        de la semana y la hora real de `dt`, en la zona horaria del propio
        calendario. Esto resuelve el cruce de medianoche sin lógica
        adicional, porque Odoo ya parte un turno que cruza medianoche en
        dos líneas de asistencia (un dayofweek cada una) con el mismo
        nombre.
        """
        vacio = self.env['resource.calendar.attendance']
        result = {'shift_name': False, 'is_planned': False, 'attendance': vacio}

        calendar = workcenter.resource_calendar_id
        if not calendar or not dt:
            return result

        tz = pytz.timezone(calendar.tz or 'UTC')
        dt_utc = pytz.utc.localize(dt) if dt.tzinfo is None else dt
        dt_local = dt_utc.astimezone(tz)

        weekday = str(dt_local.weekday())  # Odoo: '0'=lunes ... '6'=domingo
        hour_float = dt_local.hour + dt_local.minute / 60.0 + dt_local.second / 3600.0
        fecha = dt_local.date()

        candidatas = calendar.attendance_ids.filtered(
            lambda a: a.dayofweek == weekday
            and a.hour_from <= hour_float < a.hour_to
            and (not a.date_from or a.date_from <= fecha)
            and (not a.date_to or a.date_to >= fecha)
        ).sorted('sequence')

        if not candidatas:
            return result

        linea = candidatas[0]
        result['shift_name'] = linea.name
        result['is_planned'] = linea.day_period != 'lunch'
        result['attendance'] = linea
        return result

    @api.model
    def shift_total_hours(self, workcenter, shift_name, fecha):
        """Horas totales de un turno, sumando TODAS sus líneas vigentes.

        Un turno partido por cruce de medianoche (dos líneas con distinto
        `dayofweek` pero el mismo `name`) se suma correctamente sin lógica
        especial: solo se filtra por nombre exacto y vigencia en `fecha`.

        :param workcenter: registro único de mrp.workcenter
        :param shift_name: nombre exacto del turno, p. ej. "Lunes Turno 3"
        :param fecha: date — determina qué versión del calendario aplica
        :return: float, horas totales del turno
        """
        calendar = workcenter.resource_calendar_id
        if not calendar or not shift_name:
            return 0.0

        lineas = calendar.attendance_ids.filtered(
            lambda a: a.name == shift_name
            and (not a.date_from or a.date_from <= fecha)
            and (not a.date_to or a.date_to >= fecha)
        )
        return sum(l.hour_to - l.hour_from for l in lineas)
