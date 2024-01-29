from odoo import api, models,fields
from odoo.exceptions import UserError
from odoo import exceptions
import logging 
_logger = logging.getLogger(__name__)

class CreditLimitConfig(models.TransientModel):
	_inherit = 'res.config.settings'
	_name = 'credit.limit.config'
	_description = "Credit Control Config"

	default_my_credit_limit = fields.Float(default_model='res.partner')
	include_not_invoiced    = fields.Boolean(string='Considere Incluir Órdenes de Venta aún no Facturadas')
	force_limit_fresh_orders    = fields.Boolean(string='Aplicar el Límite de Crédito Incluso para Clientes sin Facturas Impagas')
	
	@api.model
	def get_values(self):
		res = super(CreditLimitConfig, self).get_values()
		params = self.env['ir.config_parameter'].sudo()
		res.update(
			include_not_invoiced=params.get_param('credit.limit.include.not.invoiced'),
			force_limit_fresh_orders=params.get_param('credit.limit.force_limit_fresh_orders'),
		)
		return res
	@api.model
	def set_values(self):
		super(CreditLimitConfig, self).set_values()
		self.env['ir.config_parameter'].sudo().set_param("credit.limit.include.not.invoiced", self.include_not_invoiced)      
		self.env['ir.config_parameter'].sudo().set_param("credit.limit.force_limit_fresh_orders", self.force_limit_fresh_orders)
