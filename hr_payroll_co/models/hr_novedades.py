# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

from odoo.addons import decimal_precision as dp

class HrNovedades(models.Model):
    _name= 'hr.novedades'
    _description = 'Novedades de nómina'
       
    input_id = fields.Many2one('hr.payslip.input.type','Tipo entrada', required=True, help="Código o nombre de la novedad")
    employee_id = fields.Many2one('hr.employee','Empleado', required=True, domain=[('active','=','true')],help="Cédula o nombre completo del empleado")
    date_from = fields.Date('Fecha desde', required = True)
    date_to = fields.Date('Fecha hasta', required = True)              
    value = fields.Float('Valor', required = True, default=0.0)
    account_analytic_id = fields.Many2one('account.analytic.account','Cuenta analítica') 
    state = fields.Selection([
        ('draft', 'A enviar'),
        ('confirm', 'Para aprobar'),
        ('refuse', 'Rechazado'),
        ('validate', 'Aprobado')
        ], string='Estado', store=True, tracking=True, copy=False, readonly=False,
        help="The status is set to 'To Submit', when a time off request is created." +
        "\nThe status is 'To Approve', when time off request is confirmed by user." +
        "\nThe status is 'Refused', when time off request is refused by manager." +
        "\nThe status is 'Approved', when time off request is approved by manager.") 
    company_id = fields.Many2one(
            'res.company',
            string='Compañia',
            required=True,
            default=lambda self: self.env.user.company_id.id,
            readonly=True,
            states={'draft': [('readonly', False)]},
        )
    
    _sql_constraints = [('novedad_uniq', 'unique(company_id, input_id, date_from, date_to, employee_id, account_analytic_id)', 'La novedad debe ser unica para el periodo y cedula'),
                       ]   
