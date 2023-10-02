# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time
from datetime import datetime, timedelta, time
from dateutil import relativedelta
import babel
from pytz import timezone
import pandas as pd
import base64
import json

from odoo import api, Command, fields, models, tools, _

from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError, ValidationError
from odoo.tools import ormcache
import ast


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'
    _description = 'Payslip Batches'


    def action_validate_without_calculate(self):
        payslip_verify_result = self.mapped('slip_ids').filtered(lambda slip: slip.state in ['draft'])
        for slip in payslip_verify_result:
            slip.write({'state': 'verify'})

        payslip_done_result = self.mapped('slip_ids').filtered(lambda slip: slip.state not in ['draft', 'cancel']).action_payslip_done()
        self.action_close()
        return payslip_done_result

    def action_cancel(self):
        payslip_done_result = self.mapped('slip_ids').filtered(lambda slip: slip.state in ['done'])
        for slip in payslip_done_result:
            slip.action_payslip_cancel()

        self.write({'state': 'draft'})

    def action_draft(self):
        payslip_done_result = self.mapped('slip_ids').filtered(lambda slip: slip.state in ['cancel'])
        for slip in payslip_done_result:
            slip.action_payslip_draft()

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'
    _description = 'Pay Slip'

    def compute_sheet(self):
        print('========= compute_sheet ============')
        payslips = self.filtered(lambda slip: slip.state in ['draft', 'verify'])
        # delete old payslip lines
        payslips.line_ids.unlink()
        for payslip in payslips:
            number = payslip.number or self.env['ir.sequence'].next_by_code('salary.slip')
            #Recalcula los días
            payslip._compute_worked_days_line_ids()
            #Recupera las entradas
            payslip._compute_input_line_ids()
            #lines = [(0, 0, line) for line in payslip._get_payslip_lines()]
            lines = []
            for line in payslip._get_payslip_lines():
                if abs(line['amount']) != 0:
                   lines.append((0, 0, line))

            payslip.write({'line_ids': lines, 'number': number, 'state': 'verify', 'compute_date': fields.Date.today()})
        return True

    @api.model
    def _get_attachment_types(self):
        return {
            'attachment': self.env.ref('hr_payroll_co.input_attachment_salary'),
            'assignment': self.env.ref('hr_payroll_co.input_assignment_salary'),
            'child_support': self.env.ref('hr_payroll_co.input_child_support'),
        }

    @api.depends('employee_id', 'contract_id', 'struct_id', 'date_from', 'date_to', 'struct_id')
    def _compute_input_line_ids(self):
        print('** _compute_input_line_ids')
        attachment_types = self._get_attachment_types()
        attachment_type_ids = [f.id for f in attachment_types.values()]
        for slip in self:
            if not slip.employee_id or not slip.employee_id.salary_attachment_ids or not slip.struct_id:
                lines_to_remove = slip.input_line_ids.filtered(lambda x: x.input_type_id.id in attachment_type_ids)
                slip.update({'input_line_ids': [Command.unlink(line.id) for line in lines_to_remove]})

            if slip.employee_id.salary_attachment_ids:
                lines_to_keep = slip.input_line_ids.filtered(lambda x: x.input_type_id.id not in attachment_type_ids)
                input_line_vals = [Command.clear()] + [Command.link(line.id) for line in lines_to_keep]

                valid_attachments = slip.employee_id.salary_attachment_ids.filtered(
                    lambda a: a.state == 'open' and a.date_start <= slip.date_to
                )

                # Only take deduction types present in structure
                deduction_types = list(set(valid_attachments.mapped('deduction_type')))
                struct_deduction_lines = list(set(slip.struct_id.rule_ids.mapped('code')))
                included_deduction_types = [f for f in deduction_types if attachment_types[f].code in struct_deduction_lines]
                for deduction_type in included_deduction_types:
                    if not slip.struct_id.rule_ids.filtered(lambda r: r.active and r.code == attachment_types[deduction_type].code):
                        continue
                    attachments = valid_attachments.filtered(lambda a: a.deduction_type == deduction_type)
                    amount = sum(attachments.mapped('active_amount'))
                    name = ', '.join(attachments.mapped('description'))
                    input_type_id = attachment_types[deduction_type].id
                    if amount != 0.0:
                       input_line_vals.append(Command.create({
                           'name': name,
                           'amount': amount,
                           'input_type_id': input_type_id,
                       }))
                slip.update({'input_line_ids': input_line_vals})

            slip.input_line_ids.unlink()
            novedades_ids = self.env['hr.novedades'].search([('employee_id','=',slip.employee_id.id),('date_from','=',slip.date_from),('date_to','=',slip.date_to)])    
            input_line_vals = []
            for nov in novedades_ids:
                    input_line_vals.append(Command.create({
                        'name': nov.input_id.name,
                        'amount': nov.value,
                        'input_type_id': nov.input_id.id,
                    }))
            print('input_line_vals -.-.-.-.-.-.-.-.-.-.-.-.-.',input_line_vals )
            if input_line_vals:
               slip.update({'input_line_ids': input_line_vals})

    #@api.depends('worked_days_line_ids.number_of_hours')
    #def _compute_worked_hours(self):
    #    number_days = 0
    #    for payslip in self:
    #        for wd in payslip.worked_days_line_ids:
    #            number_days = wd.number_of_days
    #            wd.number_of_hours = round((number_days * 7.833),2)

    #        print('number_days .-.-.-.-.-.-.-.-.-.-.-.-.-',number_days)    
    #        payslip.sum_worked_hours = round((number_days * 7.833),2)
    #        print('payslip.sum_worked_hours -.-.-.-.-.-.-.-.-.-.-',payslip.sum_worked_hours) 
