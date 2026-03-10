# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import DEFAULT_SERVER_DATE_FORMAT,DEFAULT_SERVER_DATETIME_FORMAT
import time
from datetime import date, datetime, timedelta
from dateutil import relativedelta, parser
import odoo.tools
from odoo.tools.translate import _


class HrPayslip(models.Model):
    _inherit = "hr.payslip"
    _description = "Nóminas"

    liquidation_line_ids = fields.One2many('hr.contract.liquidation.details', 'slip_id', string='Liquidación', readonly=True)
    liquidation_count = fields.Integer(compute='_compute_liquidation_number', string='Número de liquidaciones') 

    @api.depends('liquidation_line_ids')
    def _compute_liquidation_number(self):
        for slip in self:
            liquidation = self.env['hr.contract.liquidation'].sudo().search([('slip_id', '=',slip.id)])
            slip.liquidation_count = len(liquidation)

    def show_liquidation(self):
        self.ensure_one()
        liquidation = self.env['hr.contract.liquidation'].sudo().search([('slip_id', '=',self.id)])

        form_view_ref = self.env.ref('hr_holidays_co.hr_contract_liquidation_form_view', False)
        tree_view_ref = self.env.ref('hr_holidays_co.hr_contract_liquidation_tree_view', False)
        if liquidation:
           return {
               'name': 'Liquidación de contrato',
               'view_mode': 'tree, form',
               'view_id': False,
               'view_type': 'form',
               'res_model': 'hr.contract.liquidation',
               'type': 'ir.actions.act_window',
               'target': 'current',
               'domain': "[('id', 'in', %s)]" % liquidation.ids,
               'views': [(tree_view_ref and tree_view_ref.id or False, 'tree'), (form_view_ref and form_view_ref.id or False, 'form')],
               'context': {}
           }


    def unlink(self):
        for slip in self:
            slip_id = self.env['hr.contract.liquidation'].sudo().search([('slip_id','=',slip.id)])
            if slip_id:
              raise UserError('No se permite eliminar esta nómina %s porque es originada desde una liquidación de contrato. Primero debe desasociarle en la liquidación de contrato' % (slip.number,))
        
        return super(HrPayslip, self).unlink()

