from odoo import models, fields, api

class BiometricLog(models.Model):
    _name = 'biometric.log'
    _inherit = ['mail.thread']
    _description = 'Registro de eventos biométricos'
    _order = 'timestamp desc'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        index=True,
        ondelete='cascade',
        tracking=True
    )
    timestamp = fields.Datetime(
        string='Fecha/Hora',
        required=True,
        index=True,
        tracking=True
    )
    employee_cedula = fields.Char(
        string='Cédula',
        index=True,
        tracking=True
    )
    ip_address = fields.Char(
        string='Dirección IP',
        tracking=True
    )

    # Status REAL determinado por el sistema
    status = fields.Selection([
        ('check_in', 'Entrada'),
        ('check_out', 'Salida')
    ], string='Tipo Determinado', required=True, index=True, tracking=True)

    # Status que envió el biométrico (solo para auditoría)
    original_status = fields.Char(
        string='Status Original del Biométrico',
        help='Status que envió el dispositivo biométrico (puede ser incorrecto)',
        tracking=True
    )

    # Razón por la que se determinó ese tipo
    determination_reason = fields.Text(
        string='Razón de Determinación',
        help='Explicación de por qué se determinó como entrada o salida',
        tracking=True
    )

    # Si fue procesado o ignorado
    processed = fields.Boolean(
        string='Procesado',
        default=True,
        help='Si False, el registro fue ignorado por ser duplicado o inválido',
        tracking=True
    )

    payload = fields.Text(
        string='Datos Originales',
        help='JSON con los datos originales recibidos del biométrico',
        tracking=True
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

    def unlink(self):
        """Deja constancia en ir.logging de cada registro eliminado."""
        now = fields.Datetime.now()
        logging_vals = []
        for record in self:
            message = (
                f"Registro biométrico ID {record.id} eliminado por "
                f"{self.env.user.name} (ID {self.env.user.id}) el {now} UTC.\n"
                f"Empleado: {record.employee_id.name} (ID {record.employee_id.id})\n"
                f"Cédula: {record.employee_cedula or ''}\n"
                f"Fecha/Hora: {record.timestamp}\n"
                f"Tipo Determinado: {record.status}\n"
                f"Status Original: {record.original_status or ''}\n"
                f"Dirección IP: {record.ip_address or ''}\n"
                f"Procesado: {record.processed}\n"
                f"Razón de Determinación: {record.determination_reason or ''}\n"
                f"Datos Originales: {record.payload or ''}"
            )
            logging_vals.append({
                'name': self._name,
                'type': 'server',
                'level': 'WARNING',
                'dbname': self.env.cr.dbname,
                'path': 'biometric_attendance/models/biometric_log.py',
                'func': 'unlink',
                'line': '0',
                'message': message,
            })
        if logging_vals:
            self.env['ir.logging'].sudo().create(logging_vals)
        return super().unlink()
