from odoo import models, fields, api


class BiometricLog(models.Model):
    _name = 'biometric.log'
    _description = 'Registro de Eventos Biométricos'
    _order = 'timestamp desc'
    
    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        index=True
    )
    timestamp = fields.Datetime(
        string='Fecha y Hora',
        required=True,
        help='Fecha y hora del evento biométrico'
    )
    status = fields.Selection([
        ('check_in', 'Check In'),
        ('check_out', 'Check Out'),
    ], string='Tipo de Evento', index=True, required=True)
    payload = fields.Text(
        string='Datos Recibidos',
        help='Datos completos recibidos del dispositivo biométrico'
    )
    employee_cedula = fields.Char(
        string='Cédula del Empleado',
        help='Número de cédula del empleado'
    )
    ip_address = fields.Char(
        string='IP del Dispositivo',
        help='Dirección IP del dispositivo biométrico'
    )
    create_date = fields.Datetime(
        string='Fecha de Recepción',
        readonly=True
    )

