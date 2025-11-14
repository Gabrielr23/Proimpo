from odoo import http
from odoo.http import request

class BiometricController(http.Controller):

    @http.route('/api/biometric', type='json', auth='public', methods=['POST'], csrf=False)
    def receive_biometric_data(self, **kwargs):
        param_token = request.env['ir.config_parameter'].sudo().get_param('biometric_api.token')
        token = request.httprequest.headers.get('Authorization', '')

        if f'Bearer {param_token}' != token:
            return {'error': 'Unauthorized'}

        data = request.jsonrequest

        log_model = request.env['biometric.log'].sudo()

        for record in data:
            log_model.create({'payload': record})

            user_id = record.get('user_id')
            timestamp = record.get('timestamp')
            status = record.get('status')

            employee = request.env['hr.employee'].sudo().search([('device_id', '=', user_id)], limit=1)
            if not employee:
                continue

            attendance = request.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('check_out', '=', False)
            ], limit=1)

            if status == 'check_in':
                if not attendance:
                    request.env['hr.attendance'].sudo().create({
                        'employee_id': employee.id,
                        'check_in': timestamp
                    })
            elif status == 'check_out':
                if attendance:
                    attendance.write({'check_out': timestamp})

        return {'ok': True, 'msg': 'Registros procesados correctamente'}
