from odoo import models, fields, api

class BiometricLog(models.Model):
    _name = 'biometric.log'
    _description = 'Registro de eventos biométricos'
    _order = 'timestamp desc'
    _rec_name = 'employee_id'
    
    employee_id = fields.Many2one(
        'hr.employee', 
        string='Empleado', 
        required=True, 
        index=True,
        ondelete='cascade'
    )
    timestamp = fields.Datetime(
        string='Fecha/Hora', 
        required=True, 
        index=True
    )
    employee_cedula = fields.Char(
        string='Cédula', 
        index=True
    )
    ip_address = fields.Char(
        string='Dirección IP'
    )
    
    # Status REAL determinado por el sistema
    status = fields.Selection([
        ('check_in', 'Entrada'),
        ('check_out', 'Salida')
    ], string='Tipo Determinado', required=True, index=True)
    
    # Status que envió el biométrico (solo para auditoría)
    original_status = fields.Char(
        string='Status Original del Biométrico',
        help='Status que envió el dispositivo biométrico (puede ser incorrecto)'
    )
    
    # Razón por la que se determinó ese tipo
    determination_reason = fields.Text(
        string='Razón de Determinación',
        help='Explicación de por qué se determinó como entrada o salida'
    )
    
    # Si fue procesado o ignorado
    processed = fields.Boolean(
        string='Procesado', 
        default=True,
        help='Si False, el registro fue ignorado por ser duplicado o inválido'
    )
    
    payload = fields.Text(
        string='Datos Originales',
        help='JSON con los datos originales recibidos del biométrico'
    )
    
    # Campos computados para mejor visualización
    employee_name = fields.Char(
        related='employee_id.name',
        string='Nombre Empleado',
        store=True,
        readonly=True
    )
    
    status_display = fields.Char(
        string='Estado',
        compute='_compute_status_display',
        store=True
    )
    
    @api.depends('status', 'processed')
    def _compute_status_display(self):
        for record in self:
            if not record.processed:
                record.status_display = 'Ignorado'
            elif record.status == 'check_in':
                record.status_display = 'Entrada'
            else:
                record.status_display = 'Salida'