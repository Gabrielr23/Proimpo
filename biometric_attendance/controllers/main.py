from odoo import http
from odoo.http import request
from datetime import datetime
import logging
import pytz

_logger = logging.getLogger(__name__)


class BiometricController(http.Controller):
    
    @http.route('/api/biometric', type='http', auth='public', methods=['POST'], csrf=False)
    def receive_biometric_data(self, **kwargs):
        """
        Recibe datos biométricos y crea registros de asistencia.
        
        Payload esperado (JSON):
        [
            {
                "cedula": "1234567890",
                "timestamp": "2026-02-12 05:58:53",
                "status": "check_in"  // OPCIONAL - será ignorado y determinado automáticamente
            }
        ]
        
        Headers requeridos:
        - Content-Type: application/json
        - Authorization: Bearer {token}
        """
        try:
            # Validar autenticación
            if not self._validate_token():
                return request.make_json_response({
                    'error': 'Unauthorized',
                    'code': 401
                }, status=401)
            
            # Obtener datos usando get_json_data()
            try:
                data = request.get_json_data()
            except Exception as e:
                _logger.error(f'Error parseando JSON: {str(e)}')
                return request.make_json_response({
                    'error': 'JSON inválido o mal formado',
                    'details': str(e),
                    'code': 400
                }, status=400)
            
            # Validar datos
            validation_error = self._validate_data(data)
            if validation_error:
                return request.make_json_response(validation_error, status=400)
            
            # Procesar registros
            result = self._process_biometric_records(data)
            
            return request.make_json_response({
                'ok': True,
                'msg': 'Registros procesados correctamente',
                'processed': result['processed'],
                'skipped': result['skipped'],
                'failed': len(result['errors']),
                'errors': result['errors']
            })
            
        except Exception as e:
            _logger.error(f'Error procesando datos biométricos: {str(e)}', exc_info=True)
            return request.make_json_response({
                'error': 'Error interno del servidor',
                'details': str(e),
                'code': 500
            }, status=500)
    
    @http.route('/api/biometric/health', type='http', auth='public', methods=['GET'], csrf=False)
    def health_check(self):
        """Endpoint para verificar que el servicio está activo."""
        return request.make_json_response({
            'status': 'ok',
            'service': 'biometric_attendance',
            'version': '2.0.0',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    
    def _validate_token(self):
        """Valida el token de autorización."""
        param_token = request.env['ir.config_parameter'].sudo().get_param('biometric_attendance.api_token')
        
        if not param_token:
            _logger.warning('Token de API biométrica no configurado')
            return False
        
        token = request.httprequest.headers.get('Authorization', '')
        return f'Bearer {param_token}' == token
    
    def _validate_data(self, data):
        """Valida el formato de los datos recibidos."""
        if not data:
            return {'error': 'No se recibieron datos', 'code': 400}
        
        if not isinstance(data, list):
            return {'error': 'Los datos deben ser una lista', 'code': 400}
        
        if len(data) > 500:
            return {'error': 'Máximo 500 registros por solicitud', 'code': 400}
        
        # Solo cedula y timestamp son requeridos (status es opcional/ignorado)
        required_fields = ['cedula', 'timestamp']
        for idx, record in enumerate(data):
            if not isinstance(record, dict):
                return {'error': f'Registro {idx} no es un objeto válido', 'code': 400}
            
            missing_fields = [field for field in required_fields if field not in record]
            if missing_fields:
                return {
                    'error': f'Registro {idx} falta campos: {", ".join(missing_fields)}',
                    'code': 400
                }
            
            # Validar que cedula no esté vacía
            if not record.get('cedula') or not str(record.get('cedula')).strip():
                return {
                    'error': f'Registro {idx} tiene cédula vacía',
                    'code': 400
                }
            
            # Validar que timestamp no esté vacío
            if not record.get('timestamp') or not str(record.get('timestamp')).strip():
                return {
                    'error': f'Registro {idx} tiene timestamp vacío',
                    'code': 400
                }
        
        return None
    
    def _process_biometric_records(self, data):
        """Procesa los registros biométricos."""
        log_model = request.env['biometric.log'].sudo()
        employee_model = request.env['hr.employee'].sudo()
        attendance_model = request.env['hr.attendance'].sudo()
        
        # Pre-cargar empleados por cédula para mejor performance
        cedulas = list(set(str(record.get('cedula')).strip() for record in data))
        employees = employee_model.search([('identification_id', 'in', cedulas)])
        employee_map = {emp.identification_id: emp for emp in employees}
        
        # Obtener parámetros configurables
        min_work_time = int(
            request.env['ir.config_parameter'].sudo().get_param(
                'biometric_attendance.min_work_time_minutes', 
                default='5'
            )
        )
        
        processed = 0
        skipped = 0
        errors = []
        
        for idx, record in enumerate(data):
            try:
                cedula = str(record.get('cedula')).strip()
                timestamp_str = record.get('timestamp')
                status_original = record.get('status', 'unknown')
                direccion_ip = record.get('ip', '')
                
                # Buscar empleado por cédula
                employee = employee_map.get(cedula)
                if not employee:
                    errors.append({
                        'index': idx,
                        'cedula': cedula,
                        'error': 'Empleado no encontrado con esa cédula'
                    })
                    continue
                
                # Convertir timestamp - formato: 2026-02-12 05:58:53
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    # Intentar otros formatos comunes
                    try:
                        timestamp = datetime.strptime(timestamp_str, '%d-%m-%Y %H:%M:%S')
                    except ValueError:
                        errors.append({
                            'index': idx,
                            'cedula': cedula,
                            'error': f'Formato de timestamp inválido: {timestamp_str}. Use: YYYY-MM-DD HH:MM:SS'
                        })
                        continue
                
                # Validar que no sea fecha futura (con margen de 5 minutos por desincronización)
                now = datetime.now()
                if timestamp > now and (timestamp - now).total_seconds() > 300:  # 5 minutos
                    errors.append({
                        'index': idx,
                        'cedula': cedula,
                        'error': f'Timestamp no puede ser futuro: {timestamp_str}'
                    })
                    continue
                
                # Aplicar zona horaria del empleado
                employee_tz = employee.resource_calendar_id.tz or 'UTC'
                try:
                    tz = pytz.timezone(employee_tz)
                except Exception:
                    tz = pytz.UTC
                
                if timestamp.tzinfo is None:
                    timestamp = tz.localize(timestamp)
                timestamp_utc = timestamp.astimezone(pytz.UTC).replace(tzinfo=None)
                
                # DETERMINAR EL TIPO REAL - IGNORANDO LO QUE VENGA DEL BIOMÉTRICO
                determination = self._determine_attendance_type(
                    employee, 
                    timestamp_utc, 
                    attendance_model,
                    min_work_time
                )
                
                if determination['action'] == 'skip':
                    skipped += 1
                    errors.append({
                        'index': idx,
                        'cedula': cedula,
                        'warning': determination['reason'],
                        'skipped': True
                    })
                    # Aún así registrar en el log para auditoría
                    log_model.create({
                        'employee_id': employee.id,
                        'timestamp': timestamp_utc,
                        'employee_cedula': cedula,
                        'ip_address': direccion_ip,
                        'status': determination['type'],
                        'original_status': str(status_original),
                        'determination_reason': determination['reason'],
                        'processed': False,
                        'payload': str({'cedula': cedula, 'timestamp': timestamp_str, 'ip': direccion_ip}),
                    })
                    continue
                
                real_status = determination['type']
                
                # Registrar en el log
                log_model.create({
                    'employee_id': employee.id,
                    'timestamp': timestamp_utc,
                    'employee_cedula': cedula,
                    'ip_address': direccion_ip,
                    'status': real_status,
                    'original_status': str(status_original),
                    'determination_reason': determination.get('reason', ''),
                    'processed': True,
                    'payload': str({'cedula': cedula, 'timestamp': timestamp_str, 'ip': direccion_ip}),
                })
                
                # Procesar asistencia según el status determinado
                if real_status == 'check_in':
                    self._process_check_in(employee, timestamp_utc, attendance_model)
                elif real_status == 'check_out':
                    self._process_check_out(employee, timestamp_utc, attendance_model)
                
                processed += 1
                
            except Exception as e:
                _logger.error(f'Error procesando registro {idx}: {str(e)}', exc_info=True)
                errors.append({
                    'index': idx,
                    'cedula': record.get('cedula'),
                    'error': str(e)
                })
        
        # Commit explícito
        try:
            request.env.cr.commit()
        except Exception as e:
            _logger.error(f'Error en commit: {str(e)}')
            request.env.cr.rollback()
            raise
        
        return {
            'processed': processed,
            'skipped': skipped,
            'errors': errors
        }
    
    def _determine_attendance_type(self, employee, timestamp, attendance_model, min_work_time_minutes=5):
        """
        Determina si un registro es entrada o salida INDEPENDIENTEMENTE del status del biométrico.
        
        Reglas:
        1. Si NO hay check-in abierto → CHECK-IN
        2. Si HAY check-in abierto:
           a. Si timestamp <= check_in → DUPLICADO/ERROR (skip)
           b. Si timestamp > check_in y diferencia < min_work_time → DUPLICADO (skip)
           c. Si timestamp > check_in y diferencia >= min_work_time → CHECK-OUT
        
        Args:
            employee: Registro del empleado
            timestamp: Datetime en UTC
            attendance_model: Modelo hr.attendance
            min_work_time_minutes: Tiempo mínimo en minutos entre entrada y salida
        
        Returns:
            dict: {
                'type': 'check_in' | 'check_out',
                'action': 'process' | 'skip',
                'reason': str
            }
        """
        # Buscar último check-in sin cerrar
        open_attendance = attendance_model.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False)
        ], limit=1, order='check_in desc')
        
        # CASO 1: No hay asistencia abierta → definitivamente es ENTRADA
        if not open_attendance:
            # Verificar que no haya sido hace muy poco (evitar duplicados)
            last_attendance = attendance_model.search([
                ('employee_id', '=', employee.id),
            ], limit=1, order='check_in desc')
            
            if last_attendance and last_attendance.check_out:
                time_since_last = (timestamp - last_attendance.check_out).total_seconds() / 60
                if 0 < time_since_last < min_work_time_minutes:
                    return {
                        'type': 'check_in',
                        'action': 'skip',
                        'reason': f'Registro muy cercano a última salida ({time_since_last:.1f} min). Posible duplicado.'
                    }
            
            _logger.info(f'✓ CHECK-IN determinado para {employee.name} a las {timestamp}')
            return {
                'type': 'check_in',
                'action': 'process',
                'reason': 'No hay check-in abierto'
            }
        
        # CASO 2: Ya existe check-in abierto
        check_in_time = open_attendance.check_in
        
        # Sub-caso 2a: Timestamp es anterior o igual al check-in → ERROR
        if timestamp <= check_in_time:
            return {
                'type': 'check_out',
                'action': 'skip',
                'reason': f'Timestamp ({timestamp}) es anterior o igual al check-in existente ({check_in_time})'
            }
        
        # Sub-caso 2b: Verificar diferencia mínima (evitar lecturas duplicadas del biométrico)
        time_diff_minutes = (timestamp - check_in_time).total_seconds() / 60
        
        if time_diff_minutes < min_work_time_minutes:
            return {
                'type': 'check_out',
                'action': 'skip',
                'reason': f'Diferencia muy corta ({time_diff_minutes:.1f} min). Posible lectura duplicada del biométrico.'
            }
        
        # Sub-caso 2c: Todo bien → es CHECK-OUT
        _logger.info(f'✓ CHECK-OUT determinado para {employee.name} a las {timestamp} (trabajó {time_diff_minutes:.1f} min)')
        return {
            'type': 'check_out',
            'action': 'process',
            'reason': f'Check-in abierto desde {check_in_time}. Diferencia: {time_diff_minutes:.1f} min'
        }
    
    def _process_check_in(self, employee, timestamp, attendance_model):
        """Procesa un check-in."""
        # Verificar nuevamente que no haya check-in abierto (por si acaso)
        attendance = attendance_model.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False)
        ], limit=1, order='check_in desc')
        
        if attendance:
            _logger.warning(
                f'⚠ Empleado {employee.name} ya tiene check-in abierto desde {attendance.check_in}. '
                f'Se omite crear nuevo check-in.'
            )
            return
        
        try:
            attendance_model.create({
                'employee_id': employee.id,
                'check_in': timestamp
            })
            _logger.info(f'✓ Check-in creado para {employee.name} ({employee.identification_id}) a las {timestamp}')
        except Exception as e:
            _logger.error(f'✗ Error creando check-in para {employee.name}: {str(e)}')
            raise
    
    def _process_check_out(self, employee, timestamp, attendance_model):
        """Procesa un check-out."""
        attendance = attendance_model.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False)
        ], limit=1, order='check_in desc')
        
        if not attendance:
            _logger.warning(
                f'⚠ Empleado {employee.name} no tiene check-in abierto para cerrar. '
                f'Se omite check-out.'
            )
            return
        
        if timestamp <= attendance.check_in:
            _logger.warning(
                f'⚠ Check-out ({timestamp}) es anterior o igual al check-in ({attendance.check_in}). '
                f'Se omite.'
            )
            return
        
        try:
            # Calcular horas trabajadas
            worked_hours = (timestamp - attendance.check_in).total_seconds() / 3600
            
            attendance.write({'check_out': timestamp})
            _logger.info(
                f'✓ Check-out creado para {employee.name} ({employee.identification_id}) a las {timestamp}. '
                f'Horas trabajadas: {worked_hours:.2f}h'
            )
        except Exception as e:
            _logger.error(f'✗ Error creando check-out para {employee.name}: {str(e)}')
            raise