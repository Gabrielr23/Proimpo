# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo import models, fields, exceptions, api, _
import io
import tempfile
import binascii
import logging
from datetime import datetime, timedelta
from odoo.tools import float_round
from odoo import api, fields, models, _

class Create_Payment_Payslip(models.TransientModel):
	_name = 'create.payment.payslip'
	_description = 'Crear pago de nóminas'

	date_payment = fields.Date(string="Fecha Pago", required=True, default=fields.Date.context_today)
	journal_id = fields.Many2one('account.journal', string='Diario', required=True, domain="[('company_id', '=', company_id), ('type', 'in', ('bank'))]")
    
	def create_payment(self):
		active_ids = self.env.context.get('active_ids')
		if not active_ids:
		   active_ids = [self.env.context.get('payslip_id')]

		if not active_ids:
		   active_ids = self.env.context.get('run_slip_ids')

		for slip in self.env['hr.payslip'].browse(active_ids):
			if slip.state != 'done':
			   raise UserError('La nómina %s no se encuentra en estado Listo o contabilizada' % (slip.number, ))
	
			slip.with_context({'paid_date': self.date_payment, 'journal_paid_id': self.journal_id.id}).action_payslip_paid()	


	def open_wizard(self):
	    return {
	        'name': 'Generar pagos',
	        'type': 'ir.actions.act_window',
	        'res_model': 'create.payment.payslip',
	        'target': 'new',
	        'views': [(self.env.ref('hr_payroll_co.create_payment_payslip_form').id, 'form')],
	        'context': {'active_ids': self.env.context.get('active_ids')},
	        }
