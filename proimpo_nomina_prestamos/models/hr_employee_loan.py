# -*- coding: utf-8 -*-
import calendar
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HrEmployeeLoan(models.Model):
    _name = 'hr.employee.loan'
    _description = 'Préstamo / Libranza del empleado'
    _order = 'date desc, id desc'

    name = fields.Char(string='Referencia', required=True, default='Nuevo', copy=False)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, ondelete='cascade')
    loan_type = fields.Selection([
        ('libranza', 'Libranza'),
        ('prestamo', 'Préstamo'),
        ('otro', 'Otro descuento'),
    ], string='Tipo', required=True, default='libranza')
    partner_id = fields.Many2one('res.partner', string='Entidad / Tercero',
                                 help='Banco, cooperativa o entidad a la que se gira la libranza.')
    date = fields.Date(string='Fecha de inicio', default=fields.Date.context_today, required=True)
    note = fields.Char(string='Observación')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    amount_total = fields.Monetary(string='Valor total', required=True)
    installment_amount = fields.Monetary(string='Valor cuota por recibo', required=True,
                                         help='Valor que se descuenta cada vez que aplica (ver Frecuencia).')
    frequency = fields.Selection([
        ('recibo', 'En cada recibo (quincena)'),
        ('mensual', 'Una vez al mes (último recibo del mes)'),
    ], string='Frecuencia', required=True, default='recibo',
        help='En cada recibo: descuenta la cuota en cada quincena. '
             'Una vez al mes: descuenta solo en el recibo cuyo período termina al cierre del mes.')

    line_ids = fields.One2many('hr.employee.loan.line', 'loan_id', string='Cuotas descontadas')
    amount_paid = fields.Monetary(string='Abonado', compute='_compute_amounts', store=True)
    amount_residual = fields.Monetary(string='Saldo', compute='_compute_amounts', store=True)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('open', 'Activo'),
        ('done', 'Pagado'),
        ('cancel', 'Cancelado'),
    ], string='Estado', default='draft', required=True, copy=False)

    @api.depends('amount_total', 'line_ids.amount')
    def _compute_amounts(self):
        for loan in self:
            paid = sum(loan.line_ids.mapped('amount'))
            loan.amount_paid = paid
            loan.amount_residual = loan.amount_total - paid

    @api.constrains('amount_total', 'installment_amount')
    def _check_amounts(self):
        for loan in self:
            if loan.amount_total <= 0:
                raise ValidationError(_('El valor total debe ser mayor que cero.'))
            if loan.installment_amount <= 0:
                raise ValidationError(_('El valor de la cuota debe ser mayor que cero.'))

    def get_installment_for_date(self, date_to):
        """Cuota a descontar para un recibo cuyo período termina en date_to.
        Considera estado, saldo y frecuencia. Devuelve 0 si no aplica."""
        self.ensure_one()
        if self.state != 'open':
            return 0.0
        cuota = min(self.installment_amount, self.amount_residual)
        if cuota <= 0:
            return 0.0
        if self.frequency == 'mensual' and date_to:
            last_day = calendar.monthrange(date_to.year, date_to.month)[1]
            if date_to.day != last_day:
                return 0.0
        return cuota

    def action_open(self):
        self.write({'state': 'open'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_cancel(self):
        self.write({'state': 'cancel'})


class HrEmployeeLoanLine(models.Model):
    _name = 'hr.employee.loan.line'
    _description = 'Cuota descontada de préstamo/libranza'
    _order = 'date desc, id desc'

    loan_id = fields.Many2one('hr.employee.loan', string='Préstamo/Libranza',
                              required=True, ondelete='cascade')
    payslip_id = fields.Many2one('hr.payslip', string='Recibo', ondelete='cascade')
    employee_id = fields.Many2one(related='loan_id.employee_id', store=True)
    date = fields.Date(string='Fecha', default=fields.Date.context_today)
    amount = fields.Monetary(string='Valor descontado')
    currency_id = fields.Many2one(related='loan_id.currency_id')
