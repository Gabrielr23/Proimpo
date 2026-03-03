from odoo import models, fields, api
from datetime import datetime, timedelta
import pytz
import logging
import math

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
        string="Llegó tarde?",
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
    approved_overtime = fields.Float(
        string="HEA",
        compute="_get_limit_extras_hours",
        store=True,
        help="Horas extras aprobadas"
    )
    hd = fields.Float(
        string="HD",
        compute="_compute_discounted_hours",
        store=True,
        help="Horas descontadas por llegada tarde o salida temprana"
    )
    hdo = fields.Float(
        string="HDO",
        compute="_compute_work_hours_breakdown",
        store=True,
        help="Horas trabajadas en horario diurno ordinario (6AM-7PM) sin extras"
    )
    rn = fields.Float(
        string="RN",
        compute="_compute_work_hours_breakdown",
        store=True,
        help="Horas trabajadas en horario nocturno (7PM-6AM) sin extras"
    )
    hed = fields.Float(
        string="HED",
        compute="_compute_work_hours_breakdown",
        store=True,
        help="Horas extras trabajadas en horario diurno (6AM-7PM)"
    )
    hen = fields.Float(
        string="HEN",
        compute="_compute_work_hours_breakdown",
        store=True,
        help="Horas extras trabajadas en horario nocturno (7PM-6AM)"
    )
    hfd = fields.Float(
        string="HFD",
        compute="_compute_work_hours_breakdown",
        store=True,
        help="Horas trabajadas en festivo durante horario diurno"
    )
    rnd = fields.Float(
        string="RND",
        compute="_compute_work_hours_breakdown",
        store=True,
        help="Horas trabajadas en horario nocturno en festivo/dominical"
    )

    def _get_employee_tz(self, employee):
        """
        Retorna el objeto pytz.timezone para el empleado.
        Prioridad: calendar.tz > user.tz > 'UTC'
        """
        tz_name = 'UTC'
        calendar = employee.resource_calendar_id
        if calendar and calendar.tz:
            tz_name = calendar.tz
        elif self.env.user.tz:
            tz_name = self.env.user.tz
        return pytz.timezone(tz_name)

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

            tz = self._get_employee_tz(rec.employee_id)
            check_in_local = pytz.UTC.localize(rec.check_in).astimezone(tz)
            att_date = check_in_local.date()

            # PASO 1: Buscar primero en planning.slot
            planning_data = self._get_planning_slot(rec.employee_id, att_date, tz)
            if planning_data:
                rec.used_planning = True
                rec.planning_slot_name = planning_data.get('name', 'Turno planificado')
                expected_in_utc = planning_data.get('start')
                expected_out_utc = planning_data.get('end')
            else:
                # PASO 2: usar el horario del calendario
                calendar = rec.employee_id.resource_calendar_id
                if not calendar:
                    continue

                rec.used_planning = False
                expected_in_utc, expected_out_utc = self._get_times_from_calendar(
                    calendar, att_date, tz
                )

            if expected_in_utc and expected_out_utc:
                rec.expected_check_in = expected_in_utc
                rec.expected_check_out = expected_out_utc

                if rec.check_in:
                    rec.is_late = rec.check_in > (expected_in_utc + timedelta(minutes=1))

                if rec.check_out:
                    rec.left_early = rec.check_out < (expected_out_utc - timedelta(minutes=1))

    def _get_planning_slot(self, employee, date, tz):
        """
        Busca el turno planificado para el empleado en la fecha dada.
        Retorna un dict con name/start/end o False si no existe.
        """
        if 'planning.slot' not in self.env:
            return False

        from odoo.exceptions import MissingError, ValidationError

        try:
            date_start = tz.localize(datetime.combine(date, datetime.min.time()))
            date_end = tz.localize(datetime.combine(date, datetime.max.time()))
            date_start_utc = date_start.astimezone(pytz.UTC).replace(tzinfo=None)
            date_end_utc = date_end.astimezone(pytz.UTC).replace(tzinfo=None)

            planning_slot = self.env['planning.slot'].search([
                ('employee_id', '=', employee.id),
                ('start_datetime', '>=', date_start_utc),
                ('start_datetime', '<=', date_end_utc),
                ('state', '!=', 'cancel'),
            ], limit=1, order='start_datetime')

            if planning_slot:
                return {
                    'name': planning_slot.name or 'Turno planificado',
                    'start': planning_slot.start_datetime,
                    'end': planning_slot.end_datetime,
                }
            return False

        except (MissingError, ValidationError) as e:
            _logger.warning("Error al buscar planning slot para empleado %s en %s: %s",
                          employee.id, date, e)
            return False

    def _get_times_from_calendar(self, calendar, att_date, tz):
        """
        Obtiene las horas esperadas desde el resource.calendar.
        Retorna (expected_check_in_utc, expected_check_out_utc).
        """
        weekday = att_date.weekday()
        attendance_intervals = calendar.attendance_ids.filtered(
            lambda a: int(a.dayofweek) == weekday
        ).sorted(lambda a: a.hour_from)

        if not attendance_intervals:
            return False, False

        first_interval = attendance_intervals[0]
        last_interval = attendance_intervals[-1]

        in_hour = int(first_interval.hour_from)
        in_minute = int((first_interval.hour_from % 1) * 60)
        if in_hour >= 24:
            in_hour = in_hour % 24

        expected_in_local = tz.localize(
            datetime.combine(att_date, datetime.min.time().replace(
                hour=in_hour, minute=in_minute
            ))
        )

        out_hour = int(last_interval.hour_to)
        out_minute = int((last_interval.hour_to % 1) * 60)
        out_date = att_date

        if out_hour >= 24:
            out_hour = out_hour % 24
            out_date = att_date + timedelta(days=1)
        elif last_interval.hour_to < first_interval.hour_from:
            out_date = att_date + timedelta(days=1)

        expected_out_local = tz.localize(
            datetime.combine(out_date, datetime.min.time().replace(
                hour=out_hour, minute=out_minute
            ))
        )

        expected_check_in_utc = expected_in_local.astimezone(pytz.UTC).replace(tzinfo=None)
        expected_check_out_utc = expected_out_local.astimezone(pytz.UTC).replace(tzinfo=None)

        return expected_check_in_utc, expected_check_out_utc

    def action_recalculate_expected_times(self):
        """
        Acción para recalcular manualmente los tiempos esperados.
        """
        _logger.info("Recalculando tiempos esperados para %d registros de asistencia", len(self))
        self.invalidate_recordset([
            'expected_check_in',
            'expected_check_out',
            'is_late',
            'left_early',
            'used_planning',
            'planning_slot_name',
        ])
        self._compute_expected_times()
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

    def _round_to_half_hour(self, hours):
        """
        Redondea horas al intervalo de 30 minutos según regla personalizada.
        
        Basado en análisis de ejemplos:
        - 1:17 (77 min, 1.283h) → 1.0
        - 1:35 (95 min, 1.583h) → 1.5
        - 1:45 (105 min, 1.75h) → 1.5
        
        Patrón detectado:
        - Si los minutos están entre 0-29: redondea a .0
        - Si los minutos están entre 30-59: redondea a .5
        """
        if hours <= 0:
            return 0.0
        
        # Convertir a minutos totales
        total_minutes = hours * 60
        
        # Extraer horas completas y minutos restantes
        full_hours = int(total_minutes // 60)
        remaining_minutes = int(total_minutes % 60)
        
        # Aplicar regla de redondeo
        if remaining_minutes < 30:
            return float(full_hours)
        else:
            return full_hours + 0.5

    @api.depends('check_in', 'check_out', 'expected_check_in', 'expected_check_out')
    def _compute_discounted_hours(self):
        """
        Calcula las horas descontadas por llegada tarde o salida temprana.
        Se redondea a intervalos de 30 minutos hacia arriba.
        
        Ejemplos:
        - Llegó 1 hora tarde en turno de 8h → trabaja 7h → descuento 1.0h
        - Salió 1:45 antes → descuento 2.0h (redondeado)
        - Llegó 0:20 tarde → descuento 0.5h (redondeado)
        """
        for rec in self:
            rec.hd = 0.0

            if not rec.check_in or not rec.check_out:
                continue

            if not rec.expected_check_in or not rec.expected_check_out:
                continue

            discounted_hours = 0.0

            # 1. Llegada tarde (después de la hora esperada)
            if rec.check_in > rec.expected_check_in:
                late_hours = (rec.check_in - rec.expected_check_in).total_seconds() / 3600
                discounted_hours += late_hours

            # 2. Salida temprana (antes de la hora esperada)
            if rec.check_out < rec.expected_check_out:
                early_hours = (rec.expected_check_out - rec.check_out).total_seconds() / 3600
                discounted_hours += early_hours

            # Redondear a 30 minutos hacia arriba
            if discounted_hours > 0:
                rec.hd = self._round_to_half_hour(discounted_hours)
            # rec.hd = discounted_hours

    @api.depends('check_in', 'check_out', 'expected_check_in', 'expected_check_out')
    def _get_limit_extras_hours(self):
        """
        Calcula las horas extras aprobadas para cada registro.
        
        MEJORAS:
        - Solo asigna horas extras si realmente las hay
        - Considera entrada anticipada como hora extra
        - Redondea a intervalos de 30 minutos
        - Obtiene límite desde hr.overtime.line
        """
        for rec in self:
            rec.approved_overtime = 0.0

            if not rec.check_out or not rec.employee_id:
                continue

            # Obtener la fecha del turno en la timezone del empleado
            tz = self._get_employee_tz(rec.employee_id)
            check_in_local = pytz.UTC.localize(rec.check_in).astimezone(tz)
            turno_date = check_in_local.date()

            # Consultar el cupo aprobado para este empleado y fecha
            limite = self._get_limit_extras_hours_max(rec.employee_id, turno_date)

            # Calcular horas extras totales (entrada anticipada + salida tardía)
            extra_hours = 0.0

            # Entrada anticipada (solo si llegó ANTES de la hora esperada)
            if rec.expected_check_in and rec.check_in < rec.expected_check_in:
                early_entry = (rec.expected_check_in - rec.check_in).total_seconds() / 3600
                extra_hours += early_entry

            # Salida tardía (solo si salió DESPUÉS de la hora esperada)
            if rec.expected_check_out and rec.check_out > rec.expected_check_out:
                late_exit = (rec.check_out - rec.expected_check_out).total_seconds() / 3600
                extra_hours += late_exit

            if extra_hours > 0:
                # Redondear a 30 minutos
                extra_hours_rounded = self._round_to_half_hour(extra_hours)
                
                # Limitar al cupo aprobado
                rec.approved_overtime = round(min(extra_hours_rounded, limite), 2)

    def _get_limit_extras_hours_max(self, employee, date):
        """
        Retorna el límite máximo de horas extras permitidas para un empleado en una fecha.
        Consulta el modelo hr.overtime.line para obtener el cupo diario aprobado.
        """
        if not employee or not date:
            return 0.0

        overtime_line = self.env['hr.overtime.line'].search([
            ('employee_id', '=', employee.id),
            ('date', '=', date),
            ('company_id', '=', employee.company_id.id),
        ], limit=1)

        if overtime_line:
            return overtime_line.approved_hours

        return 0.0

    @api.depends('check_in', 'check_out', 'expected_check_in', 'expected_check_out', 'approved_overtime')
    def _compute_work_hours_breakdown(self):
        """
        Calcula el desglose de horas trabajadas según legislación colombiana.
        Incluye la entrada anticipada en el cálculo de horas extras.
        TODAS las horas se redondean a intervalos de 30 minutos.
        """
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug("Calculando desglose de horas para %d registros", len(self))

        for rec in self:
            rec.hdo = 0.0
            rec.rn = 0.0
            rec.hed = 0.0
            rec.hen = 0.0
            rec.hfd = 0.0
            rec.rnd = 0.0

            if not rec.check_in or not rec.check_out:
                continue

            tz = self._get_employee_tz(rec.employee_id)
            check_in_local = pytz.UTC.localize(rec.check_in).astimezone(tz)
            check_out_local = pytz.UTC.localize(rec.check_out).astimezone(tz)

            is_holiday = self._is_holiday_or_sunday(check_in_local.date())

            # Determinar los límites de horario ordinario y extra
            ordinary_start = check_in_local
            ordinary_end = check_out_local
            early_extra_start = None
            early_extra_end = None
            late_extra_start = None
            late_extra_end = None

            if rec.expected_check_in and rec.expected_check_out:
                expected_in_local = pytz.UTC.localize(rec.expected_check_in).astimezone(tz)
                expected_out_local = pytz.UTC.localize(rec.expected_check_out).astimezone(tz)

                # Entrada anticipada (hora extra)
                if check_in_local < expected_in_local:
                    early_extra_start = check_in_local
                    early_extra_end = expected_in_local
                    ordinary_start = expected_in_local
                # Llegada tarde (se ajusta el inicio del horario ordinario)
                elif check_in_local > expected_in_local:
                    ordinary_start = check_in_local
                
                # Salida tardía (hora extra)
                if check_out_local > expected_out_local:
                    late_extra_start = expected_out_local
                    late_extra_end = check_out_local
                    ordinary_end = expected_out_local
                # Salida temprana (se ajusta el fin del horario ordinario)
                elif check_out_local < expected_out_local:
                    ordinary_end = check_out_local
            
            # Calcular horas ordinarias (ya vienen redondeadas)
            if is_holiday:
                rec.hfd, rec.rnd = self._calculate_hours_by_shift(
                    ordinary_start, ordinary_end
                )
            else:
                rec.hdo, rec.rn = self._calculate_hours_by_shift(
                    ordinary_start, ordinary_end
                )

            # Calcular horas extras si están aprobadas
            if rec.approved_overtime > 0:
                total_extra_available = rec.approved_overtime
                extra_consumed = 0.0

                # 1. Procesar entrada anticipada primero
                if early_extra_start and early_extra_end:
                    early_hours = (early_extra_end - early_extra_start).total_seconds() / 3600
                    early_hours_rounded = self._round_to_half_hour(early_hours)
                    early_approved = min(early_hours_rounded, total_extra_available - extra_consumed)
                    
                    if early_approved > 0:
                        # Calcular el tiempo límite aprobado de entrada anticipada
                        approved_early_start = early_extra_end - timedelta(hours=early_approved)
                        
                        # Las horas ya vienen redondeadas
                        extra_diurna, extra_nocturna = self._calculate_hours_by_shift(
                            approved_early_start, early_extra_end
                        )
                        
                        if is_holiday:
                            rec.hfd += extra_diurna
                            rec.rnd += extra_nocturna
                        else:
                            rec.hed += extra_diurna
                            rec.hen += extra_nocturna
                        
                        extra_consumed += early_approved

                # 2. Procesar salida tardía
                if late_extra_start and late_extra_end and extra_consumed < total_extra_available:
                    late_hours = (late_extra_end - late_extra_start).total_seconds() / 3600
                    late_hours_rounded = self._round_to_half_hour(late_hours)
                    late_hours_remaining = total_extra_available - extra_consumed
                    late_approved = min(late_hours_rounded, late_hours_remaining)
                    
                    if late_approved > 0:
                        approved_late_end = late_extra_start + timedelta(hours=late_approved)
                        approved_late_end = min(approved_late_end, late_extra_end)
                        
                        # Las horas ya vienen redondeadas
                        extra_diurna, extra_nocturna = self._calculate_hours_by_shift(
                            late_extra_start, approved_late_end
                        )
                        
                        if is_holiday:
                            rec.hfd += extra_diurna
                            rec.rnd += extra_nocturna
                        else:
                            rec.hed += extra_diurna
                            rec.hen += extra_nocturna

    def _calculate_hours_by_shift(self, start_dt, end_dt, apply_rounding=True):
        """
        Calcula horas diurnas y nocturnas entre start_dt y end_dt.
        Horario diurno: 06:00–19:00 | Nocturno: 19:00–06:00
        
        Args:
            start_dt: datetime de inicio (con timezone)
            end_dt: datetime de fin (con timezone)
            apply_rounding: si True, redondea las horas a intervalos de 30 minutos
        
        Retorna: (horas_diurnas, horas_nocturnas)
        """
        diurna_hours = 0.0
        nocturna_hours = 0.0
        current = start_dt

        while current < end_dt:
            hour = current.hour

            # Calcular el próximo límite de segmento (diurno/nocturno)
            if 6 <= hour < 19:
                # Periodo diurno: avanzar hasta las 19:00
                next_boundary = current.replace(
                    hour=19, minute=0, second=0, microsecond=0
                )
                if next_boundary <= current:
                    next_boundary += timedelta(days=1)
            elif hour >= 19:
                # Periodo nocturno (tarde): avanzar hasta las 06:00 del día siguiente
                next_boundary = (current + timedelta(days=1)).replace(
                    hour=6, minute=0, second=0, microsecond=0
                )
            else:
                # Periodo nocturno (madrugada, hour < 6): avanzar hasta las 06:00
                next_boundary = current.replace(
                    hour=6, minute=0, second=0, microsecond=0
                )

            next_time = min(next_boundary, end_dt)
            segment_hours = (next_time - current).total_seconds() / 3600

            if 6 <= hour < 19:
                diurna_hours += segment_hours
            else:
                nocturna_hours += segment_hours

            current = next_time

        # Aplicar redondeo si está habilitado
        if apply_rounding:
            diurna_hours = self._round_to_half_hour(diurna_hours)
            nocturna_hours = self._round_to_half_hour(nocturna_hours)
        else:
            diurna_hours = round(diurna_hours, 2)
            nocturna_hours = round(nocturna_hours, 2)

        return diurna_hours, nocturna_hours

    def _is_holiday_or_sunday(self, date):
        """
        Determina si una fecha es festivo o domingo.
        """
        # Domingo
        if date.weekday() == 6:
            return True

        # Festivos: buscar en resource.calendar.leaves
        date_dt_start = datetime.combine(date, datetime.min.time())
        date_dt_end = datetime.combine(date, datetime.max.time())

        leave = self.env['resource.calendar.leaves'].search([
            ('resource_id', '=', False),  # Festivo global
            ('date_from', '<=', date_dt_end),
            ('date_to', '>=', date_dt_start),
        ], limit=1)

        return bool(leave)