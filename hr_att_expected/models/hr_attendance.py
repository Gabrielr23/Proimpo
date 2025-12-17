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
    used_planning = fields.Boolean(
        string="Usa turno planificado",
        compute="_compute_expected_times",
        store=True,
        help="Indica si se usó un turno planificado o el horario del empleado"
    )
    planning_slot_name = fields.Char(
        string="Turno",
        compute="_compute_expected_times",
        store=True,
        help="Nombre del turno planificado usado"
    )

    @api.depends('employee_id', 'check_in', 'check_out')
    def _compute_expected_times(self):
        for rec in self:
            rec.expected_check_in = False
            rec.expected_check_out = False
            rec.is_late = False
            rec.left_early = False
            rec.used_planning = False
            rec.planning_slot_name = False
            
            if not rec.employee_id or not rec.check_in:
                continue

            # Obtener la zona horaria
            tz_name = self.env.user.tz or 'UTC'
            calendar = rec.employee_id.resource_calendar_id
            if calendar and calendar.tz:
                tz_name = calendar.tz
            tz = pytz.timezone(tz_name)

            # Convertir check_in a la zona horaria local
            check_in_local = pytz.UTC.localize(rec.check_in).astimezone(tz)
            att_date = check_in_local.date()

            # PASO 1: Buscar primero en planning.slot (Turnos planificados)
            planning_data = self._get_planning_slot(rec.employee_id, att_date, tz)
            
            if planning_data:
                # Usar horarios del turno planificado
                rec.used_planning = True
                rec.planning_slot_name = planning_data.get('name', 'Turno planificado')
                expected_in_utc = planning_data.get('start')
                expected_out_utc = planning_data.get('end')
            else:
                # PASO 2: Si no hay turno planificado, usar el horario del calendario
                if not calendar:
                    continue
                
                rec.used_planning = False
                expected_in_utc, expected_out_utc = self._get_times_from_calendar(
                    calendar, att_date, tz
                )
            
            if expected_in_utc and expected_out_utc:
                rec.expected_check_in = expected_in_utc
                rec.expected_check_out = expected_out_utc
                
                # Determinar si llegó tarde
                if rec.check_in:
                    rec.is_late = rec.check_in > (expected_in_utc + timedelta(minutes=1))
                
                # Determinar si salió temprano
                if rec.check_out:
                    rec.left_early = rec.check_out < (expected_out_utc - timedelta(minutes=1))

    def _get_planning_slot(self, employee, date, tz):
        """
        Busca el turno planificado para el empleado en la fecha dada.
        Retorna un diccionario con los datos o False si no existe.
        """
        # Verificar si el módulo planning está instalado
        if 'planning.slot' not in self.env:
            return False
        
        try:
            # Convertir la fecha a datetime en UTC para la búsqueda
            date_start = tz.localize(datetime.combine(date, datetime.min.time()))
            date_end = tz.localize(datetime.combine(date, datetime.max.time()))
            
            date_start_utc = date_start.astimezone(pytz.UTC).replace(tzinfo=None)
            date_end_utc = date_end.astimezone(pytz.UTC).replace(tzinfo=None)
            
            # Buscar el turno planificado
            planning_slot = self.env['planning.slot'].search([
                ('employee_id', '=', employee.id),
                ('start_datetime', '>=', date_start_utc),
                ('start_datetime', '<=', date_end_utc),
                ('state', '!=', 'cancel')
            ], limit=1, order='start_datetime')
            
            if planning_slot:
                return {
                    'name': planning_slot.name or 'Turno planificado',
                    'start': planning_slot.start_datetime,
                    'end': planning_slot.end_datetime,
                }
            
            return False
        except Exception as e:
            _logger.warning(f"Error al buscar planning slot: {e}")
            return False

    def _get_times_from_calendar(self, calendar, att_date, tz):
        """
        Obtiene las horas esperadas desde el resource.calendar.
        Retorna (expected_check_in_utc, expected_check_out_utc)
        """
        weekday = att_date.weekday()
        
        # Buscar los horarios de ese día de la semana
        attendance_intervals = calendar.attendance_ids.filtered(
            lambda a: int(a.dayofweek) == weekday
        ).sorted(lambda a: a.hour_from)
        
        if not attendance_intervals:
            return False, False

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
        
        return expected_check_in_utc, expected_check_out_utc

    def action_recalculate_expected_times(self):
        """
        Acción para recalcular manualmente los tiempos esperados.
        Puede ser llamada desde un botón o desde código.
        """
        _logger.info(f"Recalculando tiempos esperados para {len(self)} registros de asistencia")
        
        # Forzar el recálculo invalidando el cache y llamando al método compute
        self.invalidate_recordset([
            'expected_check_in', 
            'expected_check_out', 
            'is_late', 
            'left_early', 
            'used_planning',
            'planning_slot_name'
        ])
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