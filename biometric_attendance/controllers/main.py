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
                "timestamp": "2025-11-06 05:58:53",
                "status": "check_in"
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
                'errors': result['errors']
            })
            
        except Exception as e:
            _logger.error(f'Error procesando datos biométricos: {str(e)}', exc_info=True)
            return request.make_json_response({
                'error': 'Error interno del servidor',
                'code': 500
            }, status=500)
    
    @http.route('/api/biometric/health', type='http', auth='public', methods=['GET'], csrf=False)
    def health_check(self):
        """Endpoint para verificar que el servicio está activo."""
        return request.make_json_response({
            'status': 'ok',
            'service': 'biometric_attendance',
            'version': '1.0.0'
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
        
        if len(data) > 1000:
            return {'error': 'Máximo 1000 registros por solicitud', 'code': 400}
        
        required_fields = ['cedula', 'timestamp', 'status']
        for idx, record in enumerate(data):
            if not isinstance(record, dict):
                return {'error': f'Registro {idx} no es un objeto válido', 'code': 400}
            
            missing_fields = [field for field in required_fields if field not in record]
            if missing_fields:
                return {
                    'error': f'Registro {idx} falta campos: {", ".join(missing_fields)}',
                    'code': 400
                }
            
            if record['status'] not in ['check_in', 'check_out']:
                return {
                    'error': f'Registro {idx} tiene status inválido: {record["status"]}',
                    'code': 400
                }
        
        return None
    
    def _process_biometric_records(self, data):
        """Procesa los registros biométricos."""
        log_model = request.env['biometric.log'].sudo()
        employee_model = request.env['hr.employee'].sudo()
        attendance_model = request.env['hr.attendance'].sudo()
        
        # Pre-cargar empleados por cédula para mejor performance
        cedulas = list(set(record.get('cedula') for record in data))
        employees = employee_model.search([('identification_id', 'in', cedulas)])
        employee_map = {emp.identification_id: emp for emp in employees}
        
        processed = 0
        errors = []
        
        for idx, record in enumerate(data):
            try:
                cedula = record.get('cedula')
                timestamp_str = record.get('timestamp')
                status = record.get('status')
                direccion_ip = record.get('ip')
                
                # Buscar empleado por cédula
                employee = employee_map.get(cedula)
                if not employee:
                    errors.append({
                        'index': idx,
                        'cedula': cedula,
                        'error': 'Empleado no encontrado con esa cédula'
                    })
                    continue
                
                # Convertir timestamp formato: 2025-11-06 05:58:53
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except ValueError as e:
                    errors.append({
                        'index': idx,
                        'cedula': cedula,
                        'error': f'Formato de timestamp inválido. Use: YYYY-MM-DD HH:MM:SS'
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
                
                # Registrar en el log
                log_model.create({
                    'employee_id': employee.id,
                    'timestamp': timestamp_utc,
                    'employee_cedula': cedula,
                    'ip_address': direccion_ip,
                    'status': status,
                    'payload': str(record),
                })
                
                # Procesar asistencia
                if status == 'check_in':
                    self._process_check_in(employee, timestamp_utc, attendance_model)
                elif status == 'check_out':
                    self._process_check_out(employee, timestamp_utc, attendance_model)
                
                processed += 1
                
            except Exception as e:
                _logger.error(f'Error procesando registro {idx}: {str(e)}', exc_info=True)
                errors.append({
                    'index': idx,
                    'cedula': record.get('cedula'),
                    'error': str(e)
                })
        
        return {
            'processed': processed,
            'errors': errors
        }
    
    def _process_check_in(self, employee, timestamp, attendance_model):
        """Procesa un check-in."""
        attendance = attendance_model.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False)
        ], limit=1, order='check_in desc')
        
        if attendance:
            _logger.warning(
                f'Empleado {employee.name} ya tiene check-in abierto desde {attendance.check_in}'
            )
            return
        
        attendance_model.create({
            'employee_id': employee.id,
            'check_in': timestamp
        })
        _logger.info(f'Check-in creado para {employee.name} a las {timestamp}')
    
    def _process_check_out(self, employee, timestamp, attendance_model):
        """Procesa un check-out."""
        attendance = attendance_model.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False)
        ], limit=1, order='check_in desc')
        
        if not attendance:
            _logger.warning(
                f'Empleado {employee.name} no tiene check-in abierto para cerrar'
            )
            return
        
        if timestamp <= attendance.check_in:
            _logger.warning(
                f'Check-out ({timestamp}) es anterior o igual al check-in ({attendance.check_in})'
            )
            return
        
        attendance.write({'check_out': timestamp})
        _logger.info(f'Check-out creado para {employee.name} a las {timestamp}')