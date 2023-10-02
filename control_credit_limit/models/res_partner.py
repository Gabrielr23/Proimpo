# -*- coding: utf-8 -*-
 
from odoo import fields, models, api
from operator import itemgetter
import logging
_logger = logging.getLogger(__name__) 

class CreditPartner(models.Model):
	_inherit = 'res.partner'
	check_credit_limit = fields.Boolean('Controlar cupo', default=True,required=True)
	my_credit_limit = fields.Float('Crédito concedido',default=0,required=True) 
	my_credit_agent_change = fields.Boolean('Permitir al administrador modificar el límite', default=True)
	my_credit_is_over = fields.Boolean('Esta sobre el límite?', compute='compute_my_credit_is_over')
	over_limit = fields.Float('Debt over Limit', compute='compute_over_limit', search='search_over_limit')
	credit_limit_days = fields.Integer(string="Limite de días", copy=False, default=8)

	def search_over_limit(self, operation, operand):
		_logger.debug(' \n\n \t Having a shitty time here  \n\n\n'+str(self.display_name)+'\n\n\n')
		acc_type='receivable'
		   #if operator not in ('<', '=', '>', '>=', '<='):
			#return []
		#if type(operand) not in (float, int):
			#return []
		#sign = 1
		#if account_type == 'payable':
			#sign = -1
		res = self._cr.execute('''
			SELECT partner.id, SUM(aml.amount_residual),my_credit_limit
			FROM res_partner partner
			LEFT JOIN account_move_line aml ON aml.partner_id = partner.id
			RIGHT JOIN account_account acc ON aml.account_id = acc.id
			WHERE acc.internal_type = 'receivable' 
			  AND NOT acc.deprecated
			GROUP BY partner.id
			HAVING  COALESCE(SUM(aml.amount_residual), 0) > partner.my_credit_limit ''' )
		res = self._cr.fetchall()
		dd=[]
		for row in res:
					_logger.debug(' \n\n \t '+str(row))
					dd.append(row[0])
		if not res:
			return [('id', '=', '0')]
		_logger.debug(' \n\n HITMAN : \t '+str(dd))
		#return [('id', 'in', map(itemgetter(0), res))]
		return [('id' ,  'in' , dd)]

	@api.depends('credit','debit', 'my_credit_limit')
	@api.model
	def compute_over_limit(self):
		_logger.debug(' \n\n \t Calling Over Limit \n\n\n')
		for item in self:			
			item.over_limit=item.credit-item.my_credit_limit
		
	

	@api.depends('credit','debit', 'my_credit_limit')
	@api.model
	def compute_my_credit_is_over(self):
		_logger.debug(' \n\n \t CHECKING OVER LIMIT FOR CUSTOMER \n\n\n')
#		self.ensure_one();
		for item in self:
			if item.my_credit_limit<item.credit:
				item.my_credit_is_over=True
			else:
				item.my_credit_is_over=False
		
	
