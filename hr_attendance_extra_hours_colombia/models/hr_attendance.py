
from odoo import models, fields, api
from datetime import datetime, time, timedelta


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    extra_hours_diurnal = fields.Float(
        string="Horas Extra Diurnas",
        compute="_compute_extra_hours",
        store=True
    )

    extra_hours_nocturnal = fields.Float(
        string="Horas Extra Nocturnas",
        compute="_compute_extra_hours",
        store=True
    )

    @api.depends("check_in", "check_out", "employee_id")
    def _compute_extra_hours(self):
        Param = self.env["ir.config_parameter"].sudo()

        nocturnal_start = float(Param.get_param("attendance.nocturnal_start", 21.0))
        nocturnal_end = float(Param.get_param("attendance.nocturnal_end", 6.0))
        rounding = int(Param.get_param("attendance.extra_rounding", 15))

        for att in self:
            att.extra_hours_diurnal = 0.0
            att.extra_hours_nocturnal = 0.0

            if not att.check_in or not att.check_out or not att.employee_id:
                continue

            calendar = att.employee_id.resource_calendar_id
            if not calendar:
                continue

            worked_end = att.check_out
            planned_start, planned_end = self._get_planned_range(calendar, att.check_in)

            if not planned_end or worked_end <= planned_end:
                continue

            self._split_colombian_hours(
                planned_end,
                worked_end,
                nocturnal_start,
                nocturnal_end,
                att
            )

            att.extra_hours_diurnal = self._round_hours(att.extra_hours_diurnal, rounding)
            att.extra_hours_nocturnal = self._round_hours(att.extra_hours_nocturnal, rounding)

    def _get_planned_range(self, calendar, ref_dt):
        weekday = str(ref_dt.weekday())
        attendances = calendar.attendance_ids.filtered(lambda a: a.dayofweek == weekday)
        if not attendances:
            return None, None

        start = min(a.hour_from for a in attendances)
        end = max(a.hour_to for a in attendances)

        date = ref_dt.date()
        return (
            datetime.combine(date, time.min) + timedelta(hours=start),
            datetime.combine(date, time.min) + timedelta(hours=end),
        )

    def _split_colombian_hours(self, start, end, noct_start, noct_end, att):
        current = start
        step = timedelta(minutes=1)

        while current < end:
            nxt = min(current + step, end)
            hour = current.hour + current.minute / 60.0
            delta = (nxt - current).total_seconds() / 3600

            if hour >= noct_start or hour < noct_end:
                att.extra_hours_nocturnal += delta
            else:
                att.extra_hours_diurnal += delta

            current = nxt

    def _round_hours(self, hours, rounding):
        minutes = hours * 60
        return round(minutes / rounding) * rounding / 60
