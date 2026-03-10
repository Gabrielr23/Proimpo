# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

from odoo.addons import decimal_precision as dp

class HrPreviousPayrolls(models.Model):
    _name= 'hr.previous.payrolls'
    _description = 'Nóminas anteriores'
    _order = 'date desc, employee_id, salary_rule_id'
       
    salary_rule_id = fields.Many2one(comodel_name='hr.salary.rule',string='Regla salarial', required=True, help="Código o nombre de la regla salaria")
    employee_id = fields.Many2one(comodel_name='hr.employee', string='Empleado', required=True, domain=[('active','=','true')],help="Cédula o nombre completo del empleado")
    date = fields.Date('Fecha', required = True)
    value = fields.Float('Valor', required = True, default=0.0)
    company_id = fields.Many2one(
            comodel_name="res.company",
            string='Compañia',
            required=True,
            default=lambda self: self.env.user.company_id.id,
            readonly=True
        )
    
 