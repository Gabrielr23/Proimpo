# -*- coding: utf-8 -*-

#from odoo import models, fields, _
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError

class AccountPayment(models.Model):
    _inherit = "account.payment"


    file_status = fields.Selection([('no_generado', 'No Generado'),
                                    ('generado', 'Generado')],default="no_generado", string="Archivo")
    bank = fields.Selection([('bancolombia', 'BanColombia'),
                             ('otros', 'Otros')],default="otros", string="Banco")



    @api.model_create_multi
    def create(self, vals_list):
        res = super(AccountPayment, self).create(vals_list)
        
        for pay in res:
            if pay.partner_bank_id.bank_id.bic == '007':
                pay.bank = 'bancolombia'
            else:
                pay.bank = 'otros'

        return res    
    



    #@api.onchange('state')
    #def onchange_state_bank(self):
    #    _logger.info("on payment state change: %s", self.state)
    #    print('empieza ---------------------------------')
    #    if self.state == 'posted':
    #        if self.partner_bank_id.id.bank_id.bic == '007':
    #            self.bank == 'bancolombia'
    #        else:
    #            self.bank == 'otros'            