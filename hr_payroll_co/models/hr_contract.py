# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.addons import decimal_precision as dp
from odoo.tools import ormcache
import ast

class HrContractParameterValue(models.Model):
    _name= 'hr.contract.parameter.value'
    _description = 'Configuración contrato'
    _order = 'date_from desc'

    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade', select=True)                        
    rule_parameter_id = fields.Many2one('hr.rule.parameter', string='Parámetro', required=True, ondelete='cascade')
    code = fields.Char(related="rule_parameter_id.code", index=True, store=True, readonly=True)
    data_type = fields.Selection(related="rule_parameter_id.data_type", index=True, store=True, readonly=True)
    date_from = fields.Date(string="Desde", index=True, required=True)
    parameter_text = fields.Text(help="Python data structure",string='Texto')
    parameter_float = fields.Float(help="Python data structure",string='Valor')
    parameter_boolean = fields.Boolean(help="Python data structure",string='Booleano')
    parameter_date = fields.Date(help="Python data structure",string='Fecha')
    parameter_partner_id = fields.Many2one('res.partner', string='Asociado')
    parameter_account_id = fields.Many2one('account.account', string='Cuenta contable')

    _sql_constraints = [('_unique', 'unique (contract_id, rule_parameter_id, date_from)', "Ya existe este parámetro para este contrato"),]


class HrContract(models.Model):
   
    _inherit = 'hr.contract'
    _description = 'Contratos'

    setting_ids = fields.One2many('hr.contract.parameter.value', 'contract_id', string=u'Configuración',)
    area_contable = fields.Selection([('A', 'Administrativa'),
                                      ('C', 'Comercial'),  
                                      ('O', 'Operativa'),], string='Area contable', required=True, default='A')       


    @api.model
    def get_rule_parameter(self, code, payslip):
        print('** get_rule_parameter at contract')

        for contract in self:
            if not payslip.to_date:
               date = fields.Date.today()
            else:
               date = payslip.to_date   

            rule_parameter = self.env['hr.contract.parameter.value'].search([
               ('contract_id', '=', contract.id),
               ('code', '=', code),
               ('date_from', '<=', date)], limit=1)

            if rule_parameter:
               #return ast.literal_eval(rule_parameter.parameter_value)
               if rule_parameter.data_type == 'T':
                  return rule_parameter.parameter_text
               if rule_parameter.data_type == 'N':
                  return rule_parameter.parameter_float        
               if rule_parameter.data_type == 'B':
                  return rule_parameter.parameter_boolean
               if rule_parameter.data_type == 'F':
                  return rule_parameter.parameter_date      
               if rule_parameter.data_type == 'A':
                  return rule_parameter.parameter_partner_id
               if rule_parameter.data_type == 'C':
                  return rule_parameter.parameter_account_id                                          
            else:
               # Si no lo encuentra en el contrato, entonces lo busca en la parametrización de la regla 
               return payslip.rule_parameter(code)       