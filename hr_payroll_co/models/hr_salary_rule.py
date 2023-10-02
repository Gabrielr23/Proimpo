# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrSalaryRuleRegister(models.Model):
    _name = 'hr.salary.rule.register'
    _description = 'Contribution Register'

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env['res.company']._company_default_get())
    need_partner_id = fields.Boolean(string='Partner en el Contrato')
    name = fields.Char(required=True)
    register_line_ids = fields.One2many('hr.salary.rule', 'register_id', string='Register Line', readonly=True)
    note = fields.Text(string='Description')

class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'
    _description = 'Salary Rule'
        
    register_id = fields.Many2one('hr.salary.rule.register', string='Registro')
    struct_id = fields.Many2one('hr.payroll.structure', string="Salary Structure", required=False)
    when_apply = fields.Selection([('forever','Siempre'), ('1','Primera quincena'),('16','Segunda quincena')],'Aplicar', required=True, default='forever')

    account_debit_comercial = fields.Many2one('account.account', 'Cuenta deudora comercial', company_dependent=True, domain=[('deprecated', '=', False)])
    account_credit_comercial = fields.Many2one('account.account', 'Cuenta acreedora comercial', company_dependent=True, domain=[('deprecated', '=', False)])

    account_debit_operativa = fields.Many2one('account.account', 'Cuenta deudora operativa', company_dependent=True, domain=[('deprecated', '=', False)])
    account_credit_operativa = fields.Many2one('account.account', 'Cuenta acreedora operativa', company_dependent=True, domain=[('deprecated', '=', False)])

    debit_partner = fields.Many2one('hr.rule.parameter', 'Tipo tercero débito', domain=[('data_type', '=', 'A')])
    credit_partner = fields.Many2one('hr.rule.parameter', 'Tipo tercero crédito', domain=[('data_type', '=', 'A')])


    def apply_rule(self, date):
        if not date:
           #raise UserError() 
           return False 