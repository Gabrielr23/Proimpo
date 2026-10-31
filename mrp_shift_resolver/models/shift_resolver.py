# -*- coding: utf-8 -*-
from datetime import timedelta

import pytz

from odoo import api, models


class MrpShiftResolver(models.AbstractModel):
    _name = 'mrp.shift.resolver'
    _description = ('Resuelve a qué turno de producción pertenece una fecha/hora, '
                    'según el calendario del centro de trabajo. Sin tabla propia: '
                    'es lógica compartida que consumen mrp_oee_report, '
                    'mrp_oee_dashboard y mrp_production_alerts.')

    # ------------------------------------------------------------------
    # Resolución principal
    # ------------------------------------------------------------------
    @api.model
    def resolve_shift(self, workcenter, dt):
        """Identifica el turno al que pertenece una fecha/hora real.

        :param workcenter: registro único de mrp.workcenter
        :param dt: datetime naive en UTC (como lo entrega el ORM)
        :return: dict con shift_name, shift_date, is_planned, attendance

        - shift_name: nombre EXACTO de la línea de asistencia
          ("Lunes Turno 3"), o False si no hay calendario o la hora cae en
          un hueco del calendario.
        - shift_date: FECHA OPERATIVA del turno. Para una línea de las
          02:00 del martes que pertenece a "Lunes Turno 3", devuelve el
          lunes — no el martes. Sin esto, el OEE del lunes perdería su
          propio turno nocturno.
        - is_planned: False si day_period='lunch' (capacidad apagada por
          diseño). Nunca descarta producción real, solo indica que el
          objetivo de esa franja es 0.

        No compara contra "el día de hoy": busca por día real de la semana
        y hora real, en la zona horaria del calendario.
        """
        vacio = self.env['resource.calendar.attendance']
        result = {'shift_name': False, 'shift_date': False,
                  'is_planned': False, 'attendance': vacio}

        calendar = workcenter.resource_calendar_id if workcenter else False
        if not calendar or not dt:
            return result

        tz = pytz.timezone(calendar.tz or 'UTC')
        dt_utc = pytz.utc.localize(dt) if dt.tzinfo is None else dt
        dt_local = dt_utc.astimezone(tz)

        weekday = str(dt_local.weekday())  # Odoo: '0'=lunes ... '6'=domingo
        hour_float = dt_local.hour + dt_local.minute / 60.0 + dt_local.second / 3600.0
        fecha_local = dt_local.date()

        vigentes = self._vigentes(calendar, fecha_local)
        candidatas = vigentes.filtered(
            lambda a: a.dayofweek == weekday
            and a.hour_from <= hour_float < a.hour_to
        ).sorted('sequence')
        if not candidatas:
            return result

        linea = candidatas[0]
        result['shift_name'] = linea.name
        result['is_planned'] = linea.day_period != 'lunch'
        result['attendance'] = linea
        result['shift_date'] = self._fecha_operativa(vigentes, linea, fecha_local)
        return result

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------
    def _vigentes(self, calendar, fecha):
        """Líneas del calendario vigentes en una fecha dada.

        Soporta calendarios versionados: si en el futuro se crean turnos
        nuevos con date_from en lugar de editar los existentes, cada
        reporte histórico sigue leyendo la versión que estaba vigente
        entonces.
        """
        return calendar.attendance_ids.filtered(
            lambda a: (not a.date_from or a.date_from <= fecha)
            and (not a.date_to or a.date_to >= fecha)
        )

    def _fecha_operativa(self, vigentes, linea, fecha_local):
        """Fecha en que ARRANCÓ el turno al que pertenece esta hora.

        Regla estructural, sin parsear nombres de días: si la línea
        encontrada empieza a las 00:00 y existe otra línea del MISMO turno
        que termina a las 24:00, entonces esta es la continuación después
        de medianoche y el turno arrancó el día anterior.

        Se evita deliberadamente ordenar por dayofweek para deducirlo:
        "Domingo Turno 3" abarca dayofweek 6 y 0, así que el menor
        dayofweek daría el resultado equivocado al cruzar de semana.
        """
        if linea.hour_from != 0.0:
            return fecha_local
        cruza = any(
            a.name == linea.name and a.hour_to >= 24.0 for a in vigentes
        )
        return fecha_local - timedelta(days=1) if cruza else fecha_local

    @api.model
    def shift_total_hours(self, workcenter, shift_name, fecha):
        """Horas totales de un turno, sumando TODAS sus líneas vigentes.

        Un turno partido por cruce de medianoche (dos líneas, mismo
        nombre) se suma correctamente sin lógica especial.
        """
        calendar = workcenter.resource_calendar_id if workcenter else False
        if not calendar or not shift_name:
            return 0.0
        lineas = self._vigentes(calendar, fecha).filtered(
            lambda a: a.name == shift_name)
        return sum(l.hour_to - l.hour_from for l in lineas)
