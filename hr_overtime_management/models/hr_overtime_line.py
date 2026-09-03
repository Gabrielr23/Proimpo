from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HrOvertimeLine(models.Model):
    _name = "hr.overtime.line"
    _description = "Cupo Diario de Horas Extras"
    _order = "date desc"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado",
        required=True,
        ondelete="cascade",
    )

    date = fields.Date(
        string="Fecha",
        required=True,
    )

    approved_hours = fields.Float(
        string="Horas extras aprobadas",
        required=True,
    )

    @api.constrains('approved_hours')
    def _check_approved_hours_limit(self):
        for record in self:
            if record.approved_hours > 2:
                raise ValidationError(
                    'Las horas extras aprobadas no pueden exceder 2 horas diarias '
                    'según lo establecido por la ley colombiana.'
                )
            if record.approved_hours < 0:
                raise ValidationError(
                    'Las horas extras aprobadas no pueden ser negativas.'
                )

    reason = fields.Char(
        string="Motivo",
    )

    observation = fields.Text(
        string="Observación",
    )

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "unique_employee_date",
            "unique(employee_id, date, company_id)",
            "Ya existe un registro de horas extras para este empleado en esta fecha.",
        )
    ]
