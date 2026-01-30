# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, time, timedelta
import pytz


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    extra_hours_diurnal = fields.Float(
        string="Horas Extra Diurnas",
        compute="_compute_extra_hours",
        store=True,
        readonly=True,
        help="Horas extras trabajadas en horario diurno (6:00 AM - 9:00 PM)"
    )

    extra_hours_nocturnal = fields.Float(
        string="Horas Extra Nocturnas",
        compute="_compute_extra_hours",
        store=True,
        readonly=True,
        help="Horas extras trabajadas en horario nocturno (9:00 PM - 6:00 AM)"
    )

    total_extra_hours = fields.Float(
        string="Total Horas Extras",
        compute="_compute_total_extra_hours",
        store=True,
        help="Total de horas extras (diurnas + nocturnas)"
    )

    planned_hours = fields.Float(
        string="Horas Planificadas",
        compute="_compute_extra_hours",
        store=True,
        help="Horas planificadas según calendario del empleado"
    )

    @api.depends("extra_hours_diurnal", "extra_hours_nocturnal")
    def _compute_total_extra_hours(self):
        for att in self:
            att.total_extra_hours = att.extra_hours_diurnal + att.extra_hours_nocturnal

    @api.depends("check_in", "check_out", "employee_id", "employee_id.resource_calendar_id")
    def _compute_extra_hours(self):
        Param = self.env["ir.config_parameter"].sudo()

        nocturnal_start = float(Param.get_param("attendance.nocturnal_start", "21.0"))
        nocturnal_end = float(Param.get_param("attendance.nocturnal_end", "6.0"))
        rounding = int(Param.get_param("attendance.extra_rounding", "15"))

        for att in self:
            att.extra_hours_diurnal = 0.0
            att.extra_hours_nocturnal = 0.0
            att.planned_hours = 0.0

            if not att.check_in or not att.check_out or not att.employee_id:
                continue

            calendar = att.employee_id.resource_calendar_id
            if not calendar:
                continue

            # Convertir a la zona horaria del usuario/empresa
            tz = pytz.timezone(calendar.tz or 'UTC')
            check_in_tz = att.check_in.astimezone(tz) if att.check_in.tzinfo else tz.localize(att.check_in)
            check_out_tz = att.check_out.astimezone(tz) if att.check_out.tzinfo else tz.localize(att.check_out)

            # Obtener el rango planificado
            planned_start, planned_end = self._get_planned_range(calendar, check_in_tz)

            if not planned_end:
                continue

            # Calcular horas planificadas
            if planned_start and planned_end:
                att.planned_hours = (planned_end - planned_start).total_seconds() / 3600.0

            # Solo calcular horas extras si trabajó más del horario planificado
            if check_out_tz <= planned_end:
                continue

            # Calcular las horas extras desde el fin del horario planificado hasta el check-out
            self._split_colombian_hours(
                planned_end,
                check_out_tz,
                nocturnal_start,
                nocturnal_end,
                att
            )

            # Aplicar redondeo
            att.extra_hours_diurnal = self._round_hours(att.extra_hours_diurnal, rounding)
            att.extra_hours_nocturnal = self._round_hours(att.extra_hours_nocturnal, rounding)

    def _get_planned_range(self, calendar, ref_dt):
        """
        Obtiene el rango de horas planificadas para el día de referencia
        """
        weekday = str(ref_dt.weekday())
        attendances = calendar.attendance_ids.filtered(lambda a: a.dayofweek == weekday)
        
        if not attendances:
            return None, None

        # Obtener la hora de inicio más temprana y la hora de fin más tardía
        start_hour = min(a.hour_from for a in attendances)
        end_hour = max(a.hour_to for a in attendances)

        date = ref_dt.date()
        
        # Crear datetime con la zona horaria
        tz = pytz.timezone(calendar.tz or 'UTC')
        planned_start = tz.localize(datetime.combine(date, time.min) + timedelta(hours=start_hour))
        planned_end = tz.localize(datetime.combine(date, time.min) + timedelta(hours=end_hour))

        return planned_start, planned_end

    def _split_colombian_hours(self, start, end, noct_start, noct_end, att):
        """
        Divide las horas extras en diurnas y nocturnas según legislación colombiana
        """
        current = start
        step = timedelta(minutes=1)

        while current < end:
            nxt = min(current + step, end)
            hour = current.hour + current.minute / 60.0
            delta = (nxt - current).total_seconds() / 3600.0

            # Verificar si la hora está en periodo nocturno
            if hour >= noct_start or hour < noct_end:
                att.extra_hours_nocturnal += delta
            else:
                att.extra_hours_diurnal += delta

            current = nxt

    def _round_hours(self, hours, rounding):
        """
        Redondea las horas al intervalo especificado en minutos
        """
        if rounding <= 0:
            return hours
        minutes = hours * 60
        return round(minutes / rounding) * rounding / 60.0
