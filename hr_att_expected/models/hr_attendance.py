import string

from odoo import models, fields, api
from datetime import datetime, timedelta
import pytz
import logging
import math
_logger = logging.getLogger(__name__)

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'
    
    # Margen de tolerancia en minutos para llegadas tarde y salidas tempranas
    # Si el empleado llega dentro de este margen, no se considera llegada tarde
    TOLERANCE_MINUTES = 5
    
    #Se definen los campos para almacenar la información de horarios esperados, estado de llegada tarde/salida temprana, uso de planificación y desglose de horas trabajadas. Todos los campos relacionados con tiempos esperados se calculan en base al turno planificado o al horario del calendario del empleado.
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
   # Campo para horas extras aprobadas
    approved_overtime = fields.Float(
        string="HEA",
        compute="_get_limit_extras_hours",
        store=True,
        help="Horas extras aprobadas"
    )
    # Campo para horas descontadas por llegadas tarde o salidas tempranas, considerando los descansos del calendario
    hd = fields.Float(
        string="HD",
        compute="_compute_discounted_hours",
        store=True,
        help="Horas descontadas por llegada tarde o salida temprana"
    )
    # Campos para desglose de horas trabajadas
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
    # Campos para gestión de estados y razones de incosistencia
    reason_text = fields.Char(
        string="Motivo inconsistencia",
        compute='_compute_reason_text', 
        store=True
    )
    has_issue = fields.Boolean(
        compute='_compute_has_issue', 
        store=True
    )

        #Estados de asistencia
    state = fields.Selection(
        [
        ('pending', 'Pendiente'),
        ('valid', 'Valida'),
    ], string="Estado", default='pending', tracking=True)
    
    """
    Metodos y campos relacionados con la gestión de estados y razones de asistencia se agregan para permitir que los responsables de RRHH o supervisores puedan marcar manualmente registros de asistencia que requieran revisión o corrección. Esto es útil para casos donde el sistema no puede determinar automáticamente la causa de una inconsistencia (por ejemplo, falta de salida, ausencia de turno planificado, rango de horas inválido, duración sospechosa, etc.). Al marcar un registro como 'pending' y asignarle una razón, se facilita el seguimiento y la resolución de estos casos por parte del equipo encargado.
    """
    #Estados de asistencia
    reason = fields.Selection([
        ('missing_checkout', 'Falta salida'),
        ('no_planning', 'Sin turno'),
        ('invalid_range', 'Horas inválidas'),
        ('suspicious_duration', 'Duración sospechosa'),
        ('inconsistent_check_in', 'Entrada inconsistente'),
        ('inconsistent_expected_check_in', "Hora de entrada esperada no encontrada"),
    ])
    
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
            rec.state = 'valid'
            rec.reason = False
            
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
                    # Llegó tarde si supera el margen de tolerancia
                    rec.is_late = rec.check_in > (expected_in_utc + timedelta(minutes=self.TOLERANCE_MINUTES))
                
                if rec.check_out:
                    # Salió temprano si sale antes del margen de tolerancia
                    rec.left_early = rec.check_out < (expected_out_utc - timedelta(minutes=self.TOLERANCE_MINUTES))
            
                
            #CASOS PARA DEFINIR EL ESTADO DE ASISTENCIA
            if not rec.check_out:
                # Caso de salida anterior a entrada, marcar como inconsistencia
                rec.state = 'pending'
                rec.reason = 'missing_checkout'
            
            if rec.check_out and rec.check_in:
                duration = (rec.check_out - rec.check_in).total_seconds() / 3600
                if duration > 16 or duration < 1:
                    # Duración sospechosa, marcar para revisión
                    rec.state = 'pending'
                    rec.reason = 'suspicious_duration'
            
            if rec.expected_check_in and rec.check_in:
                duration = abs((rec.check_in - rec.expected_check_in)).total_seconds() / 3600
                if duration > 3:
                    # Se verifica si la entrada está muy alejada del horario esperado (más de 3 horas de diferencia)
                    rec.state = 'pending'
                    rec.reason = 'inconsistent_check_in'
            
            if not rec.expected_check_in:
                    # Si no se pudo determinar una hora de entrada esperada, marcar para revisión
                    rec.state = 'pending'
                    rec.reason = 'inconsistent_expected_check_in'
    
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
    
    def _get_work_intervals_from_calendar(self, calendar, att_date, tz):
        """
        Obtiene los intervalos de trabajo del calendario (excluyendo descansos).
        
        Retorna una lista de tuplas (start_datetime, end_datetime) en UTC sin timezone info.
        """
        weekday = att_date.weekday()
        attendance_intervals = calendar.attendance_ids.filtered(
            lambda a: int(a.dayofweek) == weekday
        ).sorted(lambda a: a.hour_from)
        
        if not attendance_intervals:
            return []
        
        work_intervals = []
        
        for interval in attendance_intervals:
            # Hora de inicio del intervalo
            start_hour = int(interval.hour_from)
            start_minute = int((interval.hour_from % 1) * 60)
            start_date = att_date
            
            if start_hour >= 24:
                start_hour = start_hour % 24
                start_date = att_date + timedelta(days=1)
            
            start_local = tz.localize(
                datetime.combine(start_date, datetime.min.time().replace(
                    hour=start_hour, minute=start_minute
                ))
            )
            
            # Hora de fin del intervalo
            end_hour = int(interval.hour_to)
            end_minute = int((interval.hour_to % 1) * 60)
            end_date = att_date
            
            if end_hour >= 24:
                end_hour = end_hour % 24
                end_date = att_date + timedelta(days=1)
            elif interval.hour_to < interval.hour_from:
                end_date = att_date + timedelta(days=1)
            
            end_local = tz.localize(
                datetime.combine(end_date, datetime.min.time().replace(
                    hour=end_hour, minute=end_minute
                ))
            )
            
            # Convertir a UTC y remover timezone info
            start_utc = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
            end_utc = end_local.astimezone(pytz.UTC).replace(tzinfo=None)
            
            work_intervals.append((start_utc, end_utc))
        
        return work_intervals
    
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
    
    def _round_to_quarter_hour(self, hours):
        """
        Redondea horas al intervalo de 15 minutos según regla personalizada.
        
        Patrón de redondeo:
        - Si los minutos están entre 0-14: redondea a .0
        - Si los minutos están entre 15-29: redondea a .25
        - Si los minutos están entre 30-44: redondea a .5
        - Si los minutos están entre 45-59: redondea a .75
        
        IMPORTANTE: Si el valor está muy cerca de una hora completa (>= 0.98),
        se redondea hacia arriba para evitar perder segundos por tolerancia.
        Ejemplo: 0.9997 horas (59min 59seg) → 1.0 horas
        """
        if hours <= 0:
            return 0.0
        
        # Si está muy cerca de una hora completa (dentro de ~1 minuto), redondear hacia arriba
        # Esto maneja casos como 0.9997 horas (59min 59seg) → 1.0 horas
        fractional_part = hours % 1
        if fractional_part >= (3600-(self.TOLERANCE_MINUTES*60))/3600:  # >= 58.8 minutos (~59 minutos)
            return float(int(hours) + 1)
        
        total_minutes = hours * 60
        full_hours = int(total_minutes // 60)
        remaining_minutes = int(total_minutes % 60)
        
        if remaining_minutes < 15:
            return float(full_hours)
        elif remaining_minutes < 30:
            return full_hours + 0.25
        elif remaining_minutes < 45:
            return full_hours + 0.5
        else:
            return full_hours + 0.75
    
    @api.depends('check_in', 'check_out', 'expected_check_in', 'expected_check_out')
    def _compute_discounted_hours(self):
        """
        Calcula las horas descontadas considerando los descansos del calendario.
        Aplica un margen de tolerancia de 5 minutos para llegadas tarde y salidas tempranas.
        
        La lógica de ajuste aquí es idéntica a la de _compute_work_hours_breakdown para
        garantizar consistencia entre HD y HDO/RN/etc.
        """
        for rec in self:
            rec.hd = 0.0
            if not rec.check_in or not rec.check_out:
                continue
            if not rec.employee_id:
                continue
            
            # Obtener intervalos de trabajo del calendario
            tz = self._get_employee_tz(rec.employee_id)
            check_in_local = pytz.UTC.localize(rec.check_in).astimezone(tz)
            att_date = check_in_local.date()
            
            calendar = rec.employee_id.resource_calendar_id
            if not calendar:
                continue
            
            work_intervals = self._get_work_intervals_from_calendar(calendar, att_date, tz)
            
            if not work_intervals:
                continue
            
            # Ajustar check_in y check_out aplicando el margen de tolerancia
            # (misma lógica que en _compute_work_hours_breakdown)
            adjusted_check_in = rec.check_in
            adjusted_check_out = rec.check_out
            
            for interval_start, interval_end in work_intervals:
                # Ajustar entrada si está dentro del margen de tolerancia
                interval_start_with_tolerance = interval_start + timedelta(minutes=self.TOLERANCE_MINUTES)
                if (rec.check_in >= interval_start and 
                    rec.check_in <= interval_start_with_tolerance and
                    rec.check_in < interval_end):
                    adjusted_check_in = interval_start
                    break
            
            for interval_start, interval_end in work_intervals:
                # Ajustar salida si está dentro del margen de tolerancia
                interval_end_with_tolerance = interval_end - timedelta(minutes=self.TOLERANCE_MINUTES)
                if (rec.check_out >= interval_end_with_tolerance and 
                    rec.check_out <= interval_end and
                    rec.check_out > interval_start):
                    adjusted_check_out = interval_end
                    break
            
            discounted_hours = 0.0
            
            # Calcular descuentos usando los tiempos ajustados
            for interval_start, interval_end in work_intervals:
                # 1. Llegada tarde a este intervalo
                if adjusted_check_in > interval_start and adjusted_check_in < interval_end:
                    # El empleado llegó tarde a este intervalo (después de aplicar tolerancia)
                    late_hours = (adjusted_check_in - interval_start).total_seconds() / 3600
                    discounted_hours += late_hours
                elif adjusted_check_in >= interval_end:
                    # El empleado llegó después de que terminó este intervalo completo
                    interval_hours = (interval_end - interval_start).total_seconds() / 3600
                    discounted_hours += interval_hours
                
                # 2. Salida temprana de este intervalo
                if adjusted_check_out < interval_end and adjusted_check_out > interval_start:
                    # El empleado salió temprano de este intervalo (después de aplicar tolerancia)
                    early_hours = (interval_end - adjusted_check_out).total_seconds() / 3600
                    discounted_hours += early_hours
                elif adjusted_check_out <= interval_start:
                    # El empleado salió antes de que comenzara este intervalo
                    interval_hours = (interval_end - interval_start).total_seconds() / 3600
                    discounted_hours += interval_hours
            
            # Redondear hacia arriba al próximo cuarto de hora
            if discounted_hours > 0:
                rec.hd = self._round_discount_to_quarter_hour(discounted_hours)
    
    @api.depends('check_in', 'check_out', 'expected_check_in', 'expected_check_out')
    def _get_limit_extras_hours(self):
        """
        Calcula las horas extras aprobadas para cada registro.
        """
        for rec in self:
            rec.approved_overtime = 0.0
            if not rec.check_out or not rec.employee_id:
                continue
            
            tz = self._get_employee_tz(rec.employee_id)
            check_in_local = pytz.UTC.localize(rec.check_in).astimezone(tz)
            turno_date = check_in_local.date()
            
            # Consultar el cupo aprobado para este empleado y fecha
            limite = self._get_limit_extras_hours_max(rec.employee_id, turno_date)
            
            # Calcular horas extras totales
            extra_hours = 0.0
            
            # Entrada anticipada
            if rec.expected_check_in and rec.check_in < rec.expected_check_in:
                early_entry = (rec.expected_check_in - rec.check_in).total_seconds() / 3600
                extra_hours += early_entry
            
            # Salida tardía
            if rec.expected_check_out and rec.check_out > rec.expected_check_out:
                late_exit = (rec.check_out - rec.expected_check_out).total_seconds() / 3600
                extra_hours += late_exit
            
            if extra_hours > 0:
                extra_hours_rounded = self._round_to_quarter_hour(extra_hours)
                rec.approved_overtime = round(min(extra_hours_rounded, limite), 2)
    
    def _get_limit_extras_hours_max(self, employee, date):
        """
        Retorna el límite máximo de horas extras permitidas.
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
        Calcula el desglose de horas trabajadas excluyendo los periodos de descanso.
        Aplica margen de tolerancia de forma consistente en todos los cálculos.
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
            
            if not rec.check_in or not rec.check_out or not rec.employee_id:
                continue
            
            tz = self._get_employee_tz(rec.employee_id)
            check_in_local = pytz.UTC.localize(rec.check_in).astimezone(tz)
            check_out_local = pytz.UTC.localize(rec.check_out).astimezone(tz)
            att_date = check_in_local.date()
            is_holiday = self._is_holiday_or_sunday(att_date)
            
            # Obtener intervalos de trabajo del calendario
            calendar = rec.employee_id.resource_calendar_id
            if not calendar:
                continue
            
            work_intervals = self._get_work_intervals_from_calendar(calendar, att_date, tz)
            
            if not work_intervals:
                continue
            
            # PASO 1: Ajustar check_in y check_out aplicando el margen de tolerancia
            # Este ajuste se usará para TODOS los cálculos (HDO, RN, HED, HEN, HFD, RND)
            adjusted_check_in = rec.check_in
            adjusted_check_out = rec.check_out
            
            for interval_start, interval_end in work_intervals:
                # Ajustar entrada si está dentro del margen de tolerancia
                interval_start_with_tolerance = interval_start + timedelta(minutes=self.TOLERANCE_MINUTES)
                if (rec.check_in >= interval_start and 
                    rec.check_in <= interval_start_with_tolerance and
                    rec.check_in < interval_end):
                    adjusted_check_in = interval_start
                    break  # Solo ajustar con el primer intervalo que coincida
            
            for interval_start, interval_end in work_intervals:
                # Ajustar salida si está dentro del margen de tolerancia
                interval_end_with_tolerance = interval_end - timedelta(minutes=self.TOLERANCE_MINUTES)
                if (rec.check_out >= interval_end_with_tolerance and 
                    rec.check_out <= interval_end and
                    rec.check_out > interval_start):
                    adjusted_check_out = interval_end
                    break  # Solo ajustar con el primer intervalo que coincida
            
            # PASO 2: Calcular horas ordinarias usando los tiempos ajustados
            for interval_start, interval_end in work_intervals:
                # Usar los tiempos ajustados para calcular el overlap
                overlap_start = max(adjusted_check_in, interval_start)
                overlap_end = min(adjusted_check_out, interval_end)
                
                # Si el empleado no trabajó en este intervalo, continuar
                if overlap_start >= overlap_end:
                    continue
                
                # Determinar si este tiempo es ordinario o extra
                is_ordinary = True
                ordinary_start = overlap_start
                ordinary_end = overlap_end
                
                if rec.expected_check_in and rec.expected_check_out:
                    # Si el intervalo está completamente fuera del horario esperado, es extra
                    if interval_end <= rec.expected_check_in or interval_start >= rec.expected_check_out:
                        is_ordinary = False
                    else:
                        # Ajustar límites ordinarios al horario esperado
                        ordinary_start = max(overlap_start, rec.expected_check_in)
                        ordinary_end = min(overlap_end, rec.expected_check_out)
                
                # Calcular horas ordinarias en este intervalo
                if is_ordinary and ordinary_start < ordinary_end:
                    ordinary_start_local = pytz.UTC.localize(ordinary_start).astimezone(tz)
                    ordinary_end_local = pytz.UTC.localize(ordinary_end).astimezone(tz)
                    
                    if is_holiday:
                        hfd_temp, rnd_temp = self._calculate_hours_by_shift(
                            ordinary_start_local, ordinary_end_local
                        )
                        rec.hfd += hfd_temp
                        rec.rnd += rnd_temp
                    else:
                        hdo_temp, rn_temp = self._calculate_hours_by_shift(
                            ordinary_start_local, ordinary_end_local
                        )
                        rec.hdo += hdo_temp
                        rec.rn += rn_temp
            
            # PASO 3: Calcular horas extras si están aprobadas
            # Las horas extras también usan los tiempos ajustados
            if rec.approved_overtime > 0:
                self._calculate_overtime_hours(rec, work_intervals, is_holiday, tz, adjusted_check_in, adjusted_check_out)
    
    def _calculate_overtime_hours(self, rec, work_intervals, is_holiday, tz, adjusted_check_in, adjusted_check_out):
        """
        Calcula las horas extras considerando tiempo FUERA de los intervalos del calendario.
        Usa los tiempos ajustados por el margen de tolerancia para consistencia.
        
        Las horas extras pueden ocurrir antes del primer intervalo o después del último intervalo.
        No dependen de los work_intervals porque el empleado puede trabajar fuera de esos horarios.
        """
        total_extra_available = rec.approved_overtime
        extra_consumed = 0.0
        
        # Entrada anticipada (ANTES del horario esperado)
        if rec.expected_check_in and adjusted_check_in < rec.expected_check_in:
            # Calcular horas extras directamente - el método _round_to_quarter_hour
            # maneja automáticamente valores cercanos a horas completas
            early_hours = (rec.expected_check_in - adjusted_check_in).total_seconds() / 3600
            early_hours_rounded = self._round_to_quarter_hour(early_hours)
            early_approved = min(early_hours_rounded, total_extra_available - extra_consumed)
            
            if early_approved > 0:
                approved_early_start = rec.expected_check_in - timedelta(hours=early_approved)
                approved_early_start_local = pytz.UTC.localize(approved_early_start).astimezone(tz)
                expected_check_in_local = pytz.UTC.localize(rec.expected_check_in).astimezone(tz)
                
                # Calcular horas extras de entrada anticipada
                extra_diurna, extra_nocturna = self._calculate_hours_by_shift(
                    approved_early_start_local, expected_check_in_local
                )
                
                _logger.info("Entrada anticipada: adjusted_check_in=%s, expected_check_in=%s, early_hours=%.6f, early_approved=%.2f, extra_diurna=%.2f, extra_nocturna=%.2f",
                           adjusted_check_in, rec.expected_check_in, early_hours, early_approved, extra_diurna, extra_nocturna)
                
                if is_holiday:
                    rec.hfd += extra_diurna
                    rec.rnd += extra_nocturna
                else:
                    rec.hed += extra_diurna
                    rec.hen += extra_nocturna
                
                extra_consumed += early_approved
        
        # Salida tardía (DESPUÉS del horario esperado)
        if rec.expected_check_out and adjusted_check_out > rec.expected_check_out and extra_consumed < total_extra_available:
            # Calcular horas extras directamente - el método _round_to_quarter_hour
            # maneja automáticamente valores cercanos a horas completas
            late_hours = (adjusted_check_out - rec.expected_check_out).total_seconds() / 3600
            late_hours_rounded = self._round_to_quarter_hour(late_hours)
            late_hours_remaining = total_extra_available - extra_consumed
            late_approved = min(late_hours_rounded, late_hours_remaining)
            
            if late_approved > 0:
                approved_late_end = rec.expected_check_out + timedelta(hours=late_approved)
                approved_late_end = min(approved_late_end, adjusted_check_out)
                
                expected_check_out_local = pytz.UTC.localize(rec.expected_check_out).astimezone(tz)
                approved_late_end_local = pytz.UTC.localize(approved_late_end).astimezone(tz)
                
                # Calcular horas extras de salida tardía
                extra_diurna, extra_nocturna = self._calculate_hours_by_shift(
                    expected_check_out_local, approved_late_end_local
                )
                
                _logger.info("Salida tardía: adjusted_check_out=%s, expected_check_out=%s, late_hours=%.6f, late_approved=%.2f, extra_diurna=%.2f, extra_nocturna=%.2f, is_holiday=%s",
                           adjusted_check_out, rec.expected_check_out, late_hours, late_approved, extra_diurna, extra_nocturna, is_holiday)
                
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
        """
        diurna_hours = 0.0
        nocturna_hours = 0.0
        current = start_dt
        
        while current < end_dt:
            hour = current.hour
            if 6 <= hour < 19:
                next_boundary = current.replace(
                    hour=19, minute=0, second=0, microsecond=0
                )
                if next_boundary <= current:
                    next_boundary += timedelta(days=1)
            elif hour >= 19:
                next_boundary = (current + timedelta(days=1)).replace(
                    hour=6, minute=0, second=0, microsecond=0
                )
            else:
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
        
        if apply_rounding:
            diurna_hours = self._round_to_quarter_hour(diurna_hours)
            nocturna_hours = self._round_to_quarter_hour(nocturna_hours)
        else:
            diurna_hours = round(diurna_hours, 2)
            nocturna_hours = round(nocturna_hours, 2)
        
        return diurna_hours, nocturna_hours
    
    def _is_holiday_or_sunday(self, date):
        """
        Determina si una fecha es festivo o domingo.
        """
        if date.weekday() == 6:
            return True
        
        date_dt_start = datetime.combine(date, datetime.min.time())
        date_dt_end = datetime.combine(date, datetime.max.time())
        
        leave = self.env['resource.calendar.leaves'].search([
            ('resource_id', '=', False),
            ('date_from', '<=', date_dt_end),
            ('date_to', '>=', date_dt_start),
        ], limit=1)
        
        return bool(leave)
    
    def _round_to_half_hour(self, hours):
        """
        Redondea horas al intervalo de 30 minutos.
        """
        if hours <= 0:
            return 0.0
        
        total_minutes = hours * 60
        full_hours = int(total_minutes // 60)
        remaining_minutes = int(total_minutes % 60)
        
        if remaining_minutes < 30:
            return float(full_hours)
        else:
            return full_hours + 0.5
    
    def _round_discount_to_quarter_hour(self, hours):
        """
        Redondea descuentos siempre hacia arriba (favorece al empleador).
        """
        if hours <= 0:
            return 0.0
        
        return math.ceil(hours * 4) / 4
    
# ========================
# COMPUTES Y MÉTODOS AUXILIARES PARA ESTADOS Y RAZONES DE ASISTENCIA
# ========================  

    @api.depends('reason')
    def _compute_reason_text(self):
        for rec in self:
            mapping = {
                'missing_checkout': "No se ha registrado la salida",
                'no_planning': "No hay turno asignado",
                'invalid_range': "El horario de entrada/salida es inválido",
                'suspicious_duration': "Duración fuera de rango, mas de 16 horas o menos de 1 hora",
                'inconsistent_check_in': "Entrada incosistente con el horario esperado",
                'inconsistent_expected_check_in': "Hora de entrada esperada incosistente"
            }
            rec.reason_text = mapping.get(rec.reason, "")

    @api.depends('state')
    def _compute_has_issue(self):
        for rec in self:
            rec.has_issue = rec.state == 'pending'