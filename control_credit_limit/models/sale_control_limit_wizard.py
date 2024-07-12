# -*- coding: utf-8 -*-

from odoo import api, models,fields
from . import sale_order
from odoo.exceptions import UserError
from odoo import exceptions
import logging
_logger = logging.getLogger(__name__) 

class SaleConfirmLimit(models.TransientModel):
	_name='sale.control.limit.wizard'
	_description = "Sale Control Limit Wizard"

	sale_order = fields.Many2one('sale.order')
	invoice_amount = fields.Float('Pedido actual',readonly=1)
	debt = fields.Float('Cartera actual',readonly=1)
	my_credit_limit = fields.Float('Crédito concedido',readonly=1)
	new_balance = fields.Float('Nuevo saldo',readonly=1)
	due_not_invoiced = fields.Float('Pedidos por facturar',readonly=1)
	#due_not_invoiced = fields.Float('Pedidos por facturar',readonly=1)
	balance_due = fields.Float('Total vencido',readonly=1)


	def agent_exceed_limit(self):
	    self.sale_order.need_approval=True
	    _logger.debug(' \n\n \t Adding USers\n\n\n')
	    group = self.env.ref('control_credit_limit.group_cartera') 
	    for myu in group.users:
	        self.sale_order.message_subscribe([myu.partner_id.id])
	        self.sale_order.message_post(body='Se solicita aprobación de pedido para un cliente con problema de límite de crédito')
                                              #subject='Order Approval is requested for a customer with Credit Limit issue')
                                              #subtype='mail.mt_comment',
                                              #type='comment')


	def exceed_limit_approve(self):
		_logger.debug(' \n\n \t Trying to approve a Sale\n\n\n')
		context = {'can_exceed_limit': 1}
		self.sale_order.with_context(context).action_confirm()
