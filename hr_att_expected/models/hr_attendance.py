from odoo import models, fields, api
from datetime import datetime, timedelta
import pytz
import logging

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    expected_check_in = fields.Datetime(
        string="Entrada esperada",
        compute="_compute_expected_times",
        store=True
    )
    expected_check_out = fields.Datetime(
        string="Salida esperada",
        compute="_compute_expected_times",
        store=True
    )
    is_late = fields.Boolean(
        string="Llegó tarde",
        compute="_compute_expected_times",
        store=True
    )
    left_early = fields.Boolean(
        string="Salió temprano",
        compute="_compute_expected_times",
        store=True
    )

    @api.depends('employee_id', 'check_in', 'check_out')
    def _compute_expected_times(self):
        for rec in self:
            rec.expected_check_in = False
            rec.expected_check_out = False
            rec.is_late = False
            rec.left_early = False
            
            if not rec.employee_id or not rec.check_in:
                continue

            # Obtener el resource calendar del empleado
            calendar = rec.employee_id.resource_calendar_id
            if not calendar:
                continue

            # Obtener la zona horaria del calendario o del usuario
            tz_name = calendar.tz or self.env.user.tz or 'UTC'
            tz = pytz.timezone(tz_name)

            # Convertir check_in a la zona horaria local
            check_in_local = pytz.UTC.localize(rec.check_in).astimezone(tz)
            att_date = check_in_local.date()
            weekday = att_date.weekday()  # lunes=0 ... domingo=6

            # Buscar los horarios de ese día de la semana
            attendance_intervals = calendar.attendance_ids.filtered(
                lambda a: int(a.dayofweek) == weekday
            ).sorted(lambda a: a.hour_from)  # Ordenar por hora de inicio
            
            if not attendance_intervals:
                continue

            # El primer intervalo define la entrada esperada
            first_interval = attendance_intervals[0]
            # El último intervalo define la salida esperada
            last_interval = attendance_intervals[-1]

            # Calcular hora de entrada esperada (SIEMPRE del PRIMER intervalo)
            in_hour = int(first_interval.hour_from)
            in_minute = int((first_interval.hour_from % 1) * 60)
            
            # Validar que las horas estén en rango válido
            if in_hour >= 24:
                in_hour = in_hour % 24
            
            expected_in_local = tz.localize(
                datetime.combine(att_date, datetime.min.time().replace(
                    hour=in_hour,
                    minute=in_minute
                ))
            )
            
            # Calcular hora de salida esperada (SIEMPRE del ÚLTIMO intervalo)
            out_hour = int(last_interval.hour_to)
            out_minute = int((last_interval.hour_to % 1) * 60)
            out_date = att_date
            
            # Si la hora es >= 24, es del día siguiente
            if out_hour >= 24:
                out_hour = out_hour % 24
                out_date = att_date + timedelta(days=1)
            # Si hour_to del último intervalo < hour_from del primer intervalo
            # es un turno nocturno (día siguiente)
            elif last_interval.hour_to < first_interval.hour_from:
                out_date = att_date + timedelta(days=1)
            
            expected_out_local = tz.localize(
                datetime.combine(out_date, datetime.min.time().replace(
                    hour=out_hour,
                    minute=out_minute
                ))
            )
            
            # Convertir a UTC para almacenar en la BD
            expected_check_in_utc = expected_in_local.astimezone(pytz.UTC).replace(tzinfo=None)
            expected_check_out_utc = expected_out_local.astimezone(pytz.UTC).replace(tzinfo=None)
            
            rec.expected_check_in = expected_check_in_utc
            rec.expected_check_out = expected_check_out_utc
            
            # Determinar si llegó tarde (usar variable local, no rec.expected_check_in)
            if rec.check_in and expected_check_in_utc:
                rec.is_late = rec.check_in > (expected_check_in_utc + timedelta(minutes=1))
            
            # Determinar si salió temprano (usar variable local, no rec.expected_check_out)
            if rec.check_out and expected_check_out_utc:
                rec.left_early = rec.check_out < (expected_check_out_utc - timedelta(minutes=1))

    def action_recalculate_expected_times(self):
        """
        Acción para recalcular manualmente los tiempos esperados.
        Puede ser llamada desde un botón o desde código.
        """
        _logger.info(f"Recalculando tiempos esperados para {len(self)} registros de asistencia")
        
        # Forzar el recálculo invalidando el cache y llamando al método compute
        self.invalidate_recordset(['expected_check_in', 'expected_check_out', 'is_late', 'left_early'])
        self._compute_expected_times()
        
        # Mensaje de confirmación para el usuario
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Recálculo completado',
                'message': f'Se recalcularon {len(self)} registros de asistencia exitosamente.',
                'type': 'success',
                'sticky': False,
            }
        }