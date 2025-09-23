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

    state = fields.Selection(selection_add=[('cancel', 'Anulado'),])

    def action_validate_without_calculate(self):
        if not self.slip_ids:
           raise UserError(_('No exite nómina para contabilizar')) 

        payslip_verify_result = self.mapped('slip_ids').filtered(lambda slip: slip.state in ['draft'])
        for slip in payslip_verify_result:
            slip.write({'state': 'verify'})

        payslip_done_result = self.mapped('slip_ids').filtered(lambda slip: slip.state not in ['draft', 'cancel']).action_payslip_done()
        self.action_close()


    def action_cancel(self):
        #if not self.slip_ids:
        #   raise UserError(_('No exite nómina para contabilizar')) 

        payslip_done_result = self.mapped('slip_ids').filtered(lambda slip: slip.state in ['done','draft'])
        for slip in payslip_done_result:
            slip.action_payslip_cancel()

        self.write({'state': 'cancel'})

    def action_draft(self):
        self.action_cancel()
        payslip_done_result = self.mapped('slip_ids').filtered(lambda slip: slip.state in ['cancel'])
        for slip in payslip_done_result:
            slip.action_payslip_draft()

        self.write({'state': 'draft'})

    def action_cancel_paid(self):
        payslip_paid_result = self.mapped('slip_ids').filtered(lambda slip: slip.state in ['paid'])
        for slip in payslip_paid_result:
            slip.action_cancel_paid()

        self.write({'state': 'close'})

    def compute_all_sheet(self):
        payslips = self.mapped('slip_ids').filtered(lambda slip: slip.state in ['draft','verify'])
        for slip in payslips:
            slip.compute_sheet()

    def action_paid(self):
        # Solo cambia el estado del lote
        self.write({'state': 'paid'})

    def action_paid_NO(self):
        # No se usa porque hay nóminas que no se pagan, entonces solo cambia el estado a pagado
        for slip in self.slip_ids:
            if slip.state != 'done':
               raise UserError('No se puede marcar el recibo de nómina %s como pagado si no está confirmado.' % (slip.number,)) 
        
        self.write({'state': 'paid'})

        return {
            'name': 'Generar pagos',
            'type': 'ir.actions.act_window',
            'res_model': 'create.payment.payslip',
            'target': 'new',
            'views': [(self.env.ref('hr_payroll_co.create_payment_payslip_form').id, 'form')],
            'context': {'run_slip_ids': self.slip_ids.ids},
            }


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'
    _description = 'Pay Slip'

    payment_id = fields.Many2one('account.payment', string='Egreso pago')
    
    def action_cancel_paid(self):
        if any(slip.state != 'paid' for slip in self):
            raise UserError(_('La nómina debe estar en estado pagado'))

        self.write({'state': 'done'})

    def compute_sheet(self):
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
    def action_payslip_paid(self):
        # Este procedimiento crea el comprobante de egreso y luego lo contabiliza
        slip_line_obj = self.env['hr.payslip.line']
        move_obj = self.env['account.move.line']
        precision = self.env['decimal.precision'].precision_get('Payroll')

        journal_id = self.env.context.get('journal_paid_id',False)
        if not journal_id:
           raise UserError('Debe primero ingresar el diario de pago')

        journal_paid_id = self.env['account.journal'].sudo().browse([journal_id])[0]

        paid_date = self.env.context.get('paid_date', False)
        if not paid_date:
           raise UserError(_('Debe primero ingresar la fecha de contabilización del pago'))
    
        for slip in self:
            #Busca el neto pagado
            slip_line_ids = slip_line_obj.search([('slip_id','=',slip.id ),('code','in',('NETO','NET'))])
            if not slip_line_ids: 
               raise UserError(_('La nómina "%s" no presenta neto a pagar. Recalcular y recontabilizar esta nómina o eliminarla') % (slip.number))

            if slip_line_ids:                              
               for line in slip_line_ids:
               
                 if line.total != 0.0:
                    line_ids = []

                    acc_id = journal_paid_id.default_account_id.id
                    if not acc_id:
                       raise UserError(_('El diario "%s" no tiene configurado la cuenta crédito!') % (slip.journal_voucher_id.name))
                                   
                    acc_id = slip.journal_id.default_account_id.id
                    if not acc_id:
                      raise UserError(_('El diario "%s" no tiene configurado la cuenta débito!')%(slip.journal_id.name))

                    # Busca la causación                    
                    lines = move_obj.search([('partner_id','=',slip.employee_id.work_contact_id.id),('move_id','=',slip.move_id.id),('account_id','=',slip.journal_id.default_account_id.id),('credit','=',line.total)])                    
                    if not lines:
                       raise UserError(_('La nómina "%s" no presenta una cuenta por pagar por valor de "%s"')%(slip.number, line.total))
                      
                    name = _('Pago nómina %s') % (slip.employee_id.name)
                    payment = {
                            'payment_type': 'outbound',
                            'date': paid_date,
                            'partner_type': 'supplier',
                            'partner_id': slip.employee_id.work_contact_id.id,
                            'ref': 'Pago nómina '+slip.number,
                            'journal_id': journal_paid_id.id,
                            'amount': line.total,
                            'payment_method_id': 1,
                    }

                    if slip.payment_id:
                       if slip.payment_id.state in ['posted','reconciled']:
                          raise UserError(_('La nómina "%s" tiene asociado el egreso "%s" validado. Debe estar en borrador o anulado') % (slip.number, slip.payment_id.name))
                        
                       if slip.payment_id.state == 'cancel':
                          slip.payment_id.action_draft()

                       slip.payment_id.write(payment)
                       payment_id = slip.payment_id

                    else:
                       payment_id = self.env['account.payment'].create(payment)
                                                                            
                    payment_id.action_post()

                    # modifica la cuenta por la cuenta por pagar de salarios                    
                    for lin in payment_id.move_id.line_ids:
                        if lin.debit != 0:
                           move = lin.move_id
                           line_id = line

                           if lin.move_id.state == 'posted':
                              lin.move_id.button_cancel()

                           lin.write({'account_id': slip.journal_id.default_account_id.id})
                           lin.move_id.post()
                           lines2rec = lin 

                           # Hace la conciliacion de la cuenta por pagar y el egreso
                           total = 0.0
                           for mov in lines:
                               lines2rec += mov
                               total = total + mov.credit
                    
                           if len(lines2rec) > 2:   
                              raise UserError(_('La nómina "%s" presenta más de una contabilización!') % (slip.number))
                    
                           diff = line.total - total 
                           if diff != 0.0:   
                              raise UserError(_('La nómina "%s" presenta una diferencia al conciliar de "%s"') % (slip.number, diff))
                                              
                           lines2rec.reconcile()                
                    
            slip.write({'payment_id': payment_id.id, 'state':'paid', 'paid_date': paid_date}) 

    def action_payslip_break_conciliation(self):
        for slip in self:
            if slip.state != 'paid':
               raise UserError("La nómina %s no se encuentra en estado pagado" % (slip.number,))

            if slip.payment_id and slip.payment_id.state == 'posted':
               slip.payment_id.action_cancel() 
               #slip.payment_id.action_draft()

            slip.write({'state': 'done'})

    def action_register_payment(self):
        return {
            'name': 'Generar pagos',
            'type': 'ir.actions.act_window',
            'res_model': 'create.payment.payslip',
            'target': 'new',
            'views': [(self.env.ref('hr_payroll_co.create_payment_payslip_form').id, 'form')],
            'context': {'payslip_id': self.id},
            }


    @api.model
    def _get_attachment_types(self):
        attachment_types = self.env['hr.salary.attachment.type'].search([])
        input_types = self.env['hr.payslip.input.type'].search([('code', 'in', attachment_types.mapped('code'))])
        missing_input_types = list(set(attachment_types.mapped('code')) - set(input_types.mapped('code')))
        if missing_input_types:
            raise UserError(_("No Other Input Type was found for the following Salary Attachment Types codes:\n%s", '\n'.join(missing_input_types)))
        result = {}
        for attachment_type in attachment_types:
            for input_type in input_types:
                if input_type.code == attachment_type.code:
                    result[attachment_type.code] = input_type
                    break
        return result

    @api.model
    def _get_attachment_types_old(self):
        return {
            'attachment': self.env.ref('hr_payroll_co.input_attachment_salary'),
            'assignment': self.env.ref('hr_payroll_co.input_assignment_salary'),
            'child_support': self.env.ref('hr_payroll_co.input_child_support'),
        }


    @api.depends('employee_id', 'contract_id', 'struct_id', 'date_from', 'date_to', 'struct_id')
    def _compute_input_line_ids(self):
        attachment_types = self._get_attachment_types()
        attachment_type_ids = [f.id for f in attachment_types.values()]
        for slip in self:
            input_line_vals = []

            if not slip.employee_id or not slip.employee_id.salary_attachment_ids or not slip.struct_id:
                lines_to_remove = slip.input_line_ids.filtered(lambda x: x.input_type_id.id in attachment_type_ids)
                slip.update({'input_line_ids': [Command.unlink(line.id) for line in lines_to_remove]})

            if slip.employee_id.salary_attachment_ids and slip.date_to:
                lines_to_remove = slip.input_line_ids.filtered(lambda x: x.input_type_id.id in attachment_type_ids)
                input_line_vals = [Command.unlink(line.id) for line in lines_to_remove]

                valid_attachments = slip.employee_id.salary_attachment_ids.filtered(
                    lambda a: a.state == 'open' and a.date_start <= slip.date_to
                )

                # Only take deduction types present in structure
                deduction_types = list(set(valid_attachments.deduction_type_id.mapped('code')))
                struct_deduction_lines = list(set(slip.struct_id.rule_ids.mapped('code')))
                included_deduction_types = [f for f in deduction_types if attachment_types[f].code in struct_deduction_lines]
                for deduction_type in included_deduction_types:
                    if not slip.struct_id.rule_ids.filtered(lambda r: r.active and r.code == attachment_types[deduction_type].code):
                        continue
                    attachments = valid_attachments.filtered(lambda a: a.deduction_type_id.code == deduction_type)
                    amount = sum(attachments.mapped('active_amount'))
                    name = ', '.join(attachments.mapped('description'))
                    input_type_id = attachment_types[deduction_type].id
                    input_line_vals.append(Command.create({
                        'name': name,
                        'amount': amount if not slip.credit_note else -amount,
                        'input_type_id': input_type_id,
                    }))

            # Incluye las novedades manuales
            novedades_ids = self.env['hr.novedades'].search([('employee_id','=',slip.employee_id.id),('date_from','=',slip.date_from),('date_to','=',slip.date_to)])    
            lines_to_remove = slip.input_line_ids.filtered(lambda x: x.novedad_id.id in novedades_ids.ids)
            lines_to_remove.unlink()

            for nov in novedades_ids:
                input_line_vals.append(Command.create({
                    'name': nov.input_id.name,
                    'amount': nov.value,
                    'input_type_id': nov.input_id.id,
                    'novedad_id': nov.id,
                }))

            if input_line_vals:
               slip.update({'input_line_ids': input_line_vals})


    @api.depends('employee_id', 'contract_id', 'struct_id', 'date_from', 'date_to', 'struct_id')
    def _compute_input_line_ids_old(self):
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

            if input_line_vals:
               slip.update({'input_line_ids': input_line_vals})


    def _get_worked_day_lines_values(self, domain=None):
        self.ensure_one()
        res = []
        hours_per_day = self._get_worked_day_lines_hours_per_day()
        work_hours = self.contract_id.get_work_hours(self.date_from, self.date_to, domain=domain)
        work_hours_ordered = sorted(work_hours.items(), key=lambda x: x[1])
        biggest_work = work_hours_ordered[-1][0] if work_hours_ordered else 0
        add_days_rounding = 0

        #Febrero
        day_to = self.date_to
        nb_of_days = 0
        if day_to.month == 2:
           if day_to.day == 28:
              nb_of_days = 2
           if day_to.day == 29:
              nb_of_days = 1

        for work_entry_type_id, hours in work_hours_ordered:
            work_entry_type = self.env['hr.work.entry.type'].browse(work_entry_type_id)
            days = round(hours / hours_per_day, 5) if hours_per_day else 0
            if work_entry_type_id == biggest_work:
                days += add_days_rounding
            day_rounded = self._round_days(work_entry_type, days)
            add_days_rounding += (days - day_rounded)
            attendance_line = {
                'sequence': work_entry_type.sequence,
                'work_entry_type_id': work_entry_type_id,
                'number_of_days': day_rounded + nb_of_days,
                'number_of_hours': hours,
            }
            res.append(attendance_line)

        # Sort by Work Entry Type sequence
        work_entry_type = self.env['hr.work.entry.type']
        return sorted(res, key=lambda d: work_entry_type.browse(d['work_entry_type_id']).sequence)


