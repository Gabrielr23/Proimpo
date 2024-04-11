# -*- coding: utf-8 -*-

from odoo import api, models,fields
from odoo.exceptions import UserError 
from odoo import exceptions
import logging
from datetime import timedelta, datetime
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
	_inherit = "sale.order"
	need_approval=fields.Boolean(string='Pending Manager\'s Approval',default=False)
	credit_limit =fields.Float(string='Customer Credit Limit',related='partner_id.my_credit_limit')
	customer_balance =fields.Monetary(string='Customer Total Balance',related='partner_id.credit')

	#@api.one
	def check_credit_limit(self):
		partner=self.partner_id

		## check if this is a customer who doesn't need to be enforced
		if not partner.check_credit_limit:
			return [1]

		## Find not invoiced sale orders
		all_so_notinv=self.env['sale.order'].search([
				('partner_id', '=', partner.id),
				('company_id', '=', self.company_id.id),
				('state', 'in', ['sale','done']),
				('invoice_status', 'in', ['to invoice']),
			])

		due_notinv = 0
		for so in all_so_notinv:
			#if so.invoice_status == 'to invoice':
			if so.state in ('sale','done') and not so.invoice_status == 'invoiced':
				due=so.amount_total
				due_notinv+=due

		
		all_invoices=self.env['account.move'].search([
				('partner_id', '=', partner.id),
				('move_type', '=', 'out_invoice'),
				('payment_state', 'not in', ['paid','in_payment']),
				('company_id', '=', self.company_id.id),
				('state', 'in', ['posted']),
			])

		all_open=0
		all_due=0.0	
		for inv in all_invoices:			
			due=inv.amount_residual
			all_due+=due
			all_open+=1
			aa='\n\nInvoice %s Due %s \n\n' % (inv.display_name, due)

		#print('facturas pendientes: ',all_due)

    # Busca solo las facturas vencidas
		all_invoices = self.env['account.move'].search([
				                 ('partner_id', '=', partner.id),
				                 ('move_type', '=', 'out_invoice'),
				                 ('company_id', '=', self.company_id.id),
				                 ('state', 'in', ['posted']),
								 ('payment_state', 'not in', ['paid','in_payment']),
				                 ('invoice_date_due','<',datetime.now())
	  							])

		all_date_due = 0.0	
		for inv in all_invoices:			
				all_date_due += inv.amount_residual
		
		new_balance=self.amount_total + all_due + due_notinv
		
		if new_balance > partner.my_credit_limit:
			params = {'sale_order':self.id,
			          'invoice_amount':self.amount_total,
			          'new_balance': new_balance,
			          'debt':partner.credit,
			          'my_credit_limit': partner.my_credit_limit,
			          'due_not_invoiced':due_notinv,
			          'balance_due' : all_date_due
			          }

			return [params]
			          
		else:
			#chequea la fecha de vencimiento
			d = timedelta(days=self.partner_id.credit_limit_days)

			self.env.cr.execute("select min(i.invoice_date_due), min(i.name) fecha from account_move i\
                             where i.state = 'posted' \
							   and i.payment_state not in ('paid','in_payment')\
                               and i.move_type = 'out_invoice' \
                               and i.partner_id = %s",(self.partner_id.id,))
                               
			
			res = self.env.cr.fetchone() or False       
			print('res ',res)

			if not res or res[0] == None:
			   _logger.debug('\n\n Showing HERE \n\n')

			   return [1]
			else:
				if res[0] != None:
					#data = datetime.strptime(res[0], "%Y-%m-%d")
					data = datetime.combine(res[0], datetime.min.time()) 
                        
					#Busca el número de la factura

					self.env.cr.execute("select i.name as fecha from account_move i\
                             where i.state = 'posted' \
                               and i.payment_state not in ('paid','in_payment')\
                               and i.move_type = 'out_invoice' \
                               and i.invoice_date_due = %s \
                               and i.partner_id = %s \
                               limit 1",(res[0], self.partner_id.id,))
                               
					res = self.env.cr.fetchone() or False   
					print('res factura: ',res)   
					#print('data ',data)
					print('d ',d)

					#if data + d < datetime.now():
					if data < datetime.now():
						#Busca el total vencido
						all_invoices = self.env['account.move'].search([('partner_id', '=', partner.id),
				                 										('move_type', '=', 'out_invoice'),
				                 										('company_id', '=', self.company_id.id),
				                 										('state', 'in', ['posted']),
																		('payment_state', 'not in', ['paid','in_payment']),
				                 										('invoice_date_due','<',datetime.now())
					  												   ])

						all_due=0.0

						for inv in all_invoices:
							all_due += inv.amount_residual

		
						params = {'sale_order':self.id,
						     	  'invoice_amount':self.amount_total,
								  'new_balance': new_balance,
								  'debt':partner.credit,
								  'my_credit_limit': partner.my_credit_limit,
								  'due_not_invoiced':due_notinv,
								  'balance_due' : all_due
							     }

						return [params]
					
					else:
						_logger.debug('\n\n Showing HERE \n\n')
						return [1]  

	@api.model
	def action_confirm(self):
		#print('** action_confirm cupos')
		_logger.debug(' \n\n \t Calling Action Confirm for a child\n\n\n')		
		for order in self:
			b=order._context.get('can_exceed_limit')
			_logger.debug(' \n\n \n My Context \n\n\n')
			_logger.debug(b)
			if b==1:
				_logger.debug(' \n\n \n Exceeding is confirmed\n\n\n')
				return super(SaleOrder, self).action_confirm()
			else:
				params=order.check_credit_limit()
				_logger.debug(params)

				if params[0]==1:
					print('params2', params[0])
					_logger.debug(' \n\n \t No Limit issue : Order can be Confirmed\n\n\n')
					return super(SaleOrder, self).action_confirm()
				else:		
					view_id=self.env['sale.control.limit.wizard']
					new = view_id.create(params[0])
					if self.env.user.has_group('control_credit_limit.group_cartera') :
						_logger.debug('Here is a manager !')
						return {
							'type': 'ir.actions.act_window',
							'name': 'Control limites de crédito',
							'res_model': 'sale.control.limit.wizard',
							'view_type': 'form',
							'view_mode': 'form',
							'res_id'    : new.id,
							'view_id': self.env.ref('control_credit_limit.my_credit_limit_confirm_wizard',False).id,
							'target': 'new',
						}
				
					else:
						return {
							'type': 'ir.actions.act_window',
							'name': 'Request Approval for Sale Order with Credit over Limit',
							'res_model': 'sale.control.limit.wizard',
							'view_type': 'form',
							'view_mode': 'form',
							'res_id'    : new.id,
							'view_id': self.env.ref('control_credit_limit.my_credit_limit_wizard',False).id,
							'target': 'new',
						}

