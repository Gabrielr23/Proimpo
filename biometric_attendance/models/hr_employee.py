from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    
    biometric_log_count = fields.Integer(
        string='Registros Biométricos',
        compute='_compute_biometric_log_count'
    )
    
    @api.depends('identification_id')
    def _compute_biometric_log_count(self):
        """Cuenta los logs biométricos del empleado."""
        for employee in self:
            if employee.identification_id:
                employee.biometric_log_count = self.env['biometric.log'].search_count([
                    ('employee_id', '=', employee.id)
                ])
            else:
                employee.biometric_log_count = 0
    
    def action_view_biometric_logs(self):
        """Abre la vista de logs biométricos del empleado."""
        self.ensure_one()
        return {
            'name': 'Registros Biométricos',
            'type': 'ir.actions.act_window',
            'res_model': 'biometric.log',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id}
        }

