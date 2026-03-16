# -*- coding:utf-8 -*-
# Copyright (C) 2024-INNOVATECSA SAS(<http://www.innovatecsa.com>).

from odoo import api, fields, models, tools, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError, ValidationError

from datetime import date, datetime, time, timedelta
from dateutil.relativedelta import relativedelta
import base64
from io import StringIO
from io import BytesIO
import xlsxwriter
import logging
import pytz
import json
from odoo.tools import date_utils
_logger = logging.getLogger(__name__)

#------------------- Liquidación prestaciones ---------------------------

class HrLiquidationConsolidated(models.Model):
    _name = 'hr.liquidation.consolidated'
    _inherit = ['mail.thread']
    _description = 'Lotes de consolidados'
    _order = 'date_liquidation desc'

    name = fields.Char(required=True, string="Nombre")
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True, copy=False,
        default=lambda self: self.env['res.company']._company_default_get()
        )

    details_ids = fields.One2many('hr.contract.liquidation.details', 'consolidated_id', string='Liquidaciones', readonly=True)
    details_count = fields.Integer(compute='_compute_details_number', string='Número de líneas')    
    novedades_count = fields.Integer(compute='_compute_novedades_number', string='Número de novedades')    
    employee_ids = fields.Many2many('hr.employee', string='Empleados')    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Confirmado'),
        ('cancel', 'Anulado'),
    ], string='Estado', index=True, readonly=True, copy=False, default='draft')

    date_liquidation = fields.Date(string='Fecha liquidación', required=True, 
        default=lambda self: fields.Date.to_string((datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()))

    date_vacaciones = fields.Date(string='Inicio vacaciones', required=False)

    liquidation_prima = fields.Boolean(string='Calcular prima', required=True, default=False)
    liquidation_cesantias = fields.Boolean(string='Calcular cesantías e intereses', required=True, default=False)
    liquidation_vacaciones = fields.Boolean(string='Calcular vacaciones', required=True, default=False)    

    @api.depends('details_ids')
    def _compute_novedades_number(self):
        for liq in self:
            novedades = []
            for line in liq.details_ids:
                if line.novedad_id:
                   novedades.append(line.novedad_id.id) 

                if line.novedad_provision_id:
                   novedades.append(line.novedad_provision_id.id) 


            liq.novedades_count = len(novedades)


    @api.depends('details_ids')
    def _compute_details_number(self):
        for liq in self:
            liq.details_count = len(liq.details_ids)

    def action_confirm(self):
        for liq in self:
            liq.state = 'done'

    def action_cancel(self):
        for liq in self:
            if liq.novedades_count > 0:
               # Elimina las novedades asociadas
               for line in self.details_ids:
                   if line.novedad_id:
                      line.novedad_id.sudo().unlink()

                   if line.novedad_provision_id:
                      line.novedad_provision_id.sudo().unlink()

                   # Si tiene nómina generada y está en borrador, entonces la recalcula
                   if line.slip_id and line.slip_id.state == 'draft': 
                      line.slip_id.compute_sheet()    

            liq.state = 'cancel'

    def action_draft(self):
        for liq in self:
            liq.state = 'draft'
                  

    def action_calculate(self):
        for liq in self:
            # Crea cada línea por empleado
            concept_ids = self.env['hr.payslip.input.type'].sudo().search([('liquidation_type','in',['V','C','IC','P'])])
            if not concept_ids:
               raise ValidationError('No han configurado el tipos de liquidación en Otros tipos de entrada') 

            if not liq.employee_ids:
               raise ValidationError('No ha seleccionado los empleados para hacer el calculo de prestaciones sociales') 

            # Borra los calculos anteriores
            liq.details_ids.unlink()

            for emp in liq.employee_ids:

                contract_id = emp.get_contract(liq.date_liquidation)
                if not contract_id:
                   raise ValidationError('No se encuentra un contrato activo para el empleado hrlcon %s' % (emp.name,))

                contract = self.env['hr.contract'].sudo().browse([contract_id])[0]
                aprendiz_lectiva = contract._get_rule_parameter('APRENDIZ_LECTIVA', liq.date_liquidation)
                aprendiz_productiva = contract._get_rule_parameter('APRENDIZ_PRODUCTIVA', liq.date_liquidation)
                integral = contract._get_rule_parameter('INTEGRAL', liq.date_liquidation)

                if aprendiz_lectiva or aprendiz_productiva:
                   raise ValidationError('No se puede calcular prestaciones al empleado %s porque es aprendiz' % (emp.name,)) 

                for concept in concept_ids:
                    date_from = False
                    if concept.liquidation_type == 'P' and not liq.liquidation_prima:
                       continue 

                    # Al salario integral no se le calcula cesantías ni intereses  
                    if concept.liquidation_type in ['C','IC'] and (not liq.liquidation_cesantias or integral):
                       continue 

                    if concept.liquidation_type == 'V' and not liq.liquidation_vacaciones:
                       continue 

                    if liq.liquidation_vacaciones and liq.date_vacaciones:
                       date_from = liq.date_vacaciones

                    contract = self.env['hr.contract'].sudo().browse([contract_id])
                    salaraio_variable = contract._get_rule_parameter('SALARIO_VARIABLE', liq.date_liquidation)   

                    vals = {
                       'consolidated_id': liq.id,
                       'employee_id': emp.id,
                       'contract_id': contract.id,
                       'average': salaraio_variable,
                       'input_type_id': concept.id,
                       'liquidation_type': concept.liquidation_type,
                       'date_from': date_from,
                       'date_to': liq.date_liquidation,
                    }    
                    detail_id = self.env['hr.contract.liquidation.details'].create(vals)
                    detail_id._calculo_campos()



    def show_details(self):
        self.ensure_one()

        form_view_ref = self.env.ref('hr_holidays_co.hr_contract_liquidation_details_form_view', False)
        tree_view_ref = self.env.ref('hr_holidays_co.hr_contract_liquidation_details_tree_view', False)
        if self.details_ids:
           return {
               'name': 'Detalle',
               'view_mode': 'tree, form',
               'view_id': False,
               'view_type': 'form',
               'res_model': 'hr.contract.liquidation.details',
               'type': 'ir.actions.act_window',
               'target': 'current',
               'domain': "[('id', 'in', %s)]" % self.details_ids.ids,
               'views': [(tree_view_ref and tree_view_ref.id or False, 'tree'), (form_view_ref and form_view_ref.id or False, 'form')],
               'context': {}
           }


    def action_create_novedades(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("hr_holidays_co.action_create_novedades_consolidated_wizard")
        return action

    def show_novedades(self):
        self.ensure_one()
        novedades = []
        for line in self.details_ids:
            if line.novedad_id:
               novedades.append(line.novedad_id.id) 

            if line.novedad_provision_id:
               novedades.append(line.novedad_provision_id.id) 

        form_view_ref = self.env.ref('hr_payroll_co.hr_novedades_view', False)
        tree_view_ref = self.env.ref('hr_payroll_co.hr_novedades_tree', False)
        if novedades:
           return {
               'name': 'Novedades de prestaciones sociales',
               'view_mode': 'tree, form',
               'view_id': False,
               'view_type': 'form',
               'res_model': 'hr.novedades',
               'type': 'ir.actions.act_window',
               'target': 'current',
               'domain': "[('id', 'in', %s)]" % novedades,
               'views': [(tree_view_ref and tree_view_ref.id or False, 'tree'), (form_view_ref and form_view_ref.id or False, 'form')],
               'context': {}
           }


    def export_xls(self):
        """Function to retrieve and open an XLS report record."""
        self.ensure_one()
        data = {
            'id': self.id,
            'model': self._name,    
            'date_stop': self.date_liquidation,        
        }

        return {
            'type': 'ir.actions.report',
            'data': {'model': 'hr.liquidation.consolidated',
                     'options': json.dumps(data,
                                           default=date_utils.json_default),
                     'output_format': 'xlsx',
                     'report_name': 'Prestaciones sociales',
                     },
            'report_type': 'stock_xlsx'
        }


    def get_xlsx_report(self, data, response):
        date_stop = datetime.strptime(data['date_stop'], "%Y-%m-%d") 

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, self.get_workbook_options())
        sheet = workbook.add_worksheet('Detalle')

        format0 = workbook.add_format({'font_size': 16, 'align': 'center', 'bold': True})
        format1 = workbook.add_format({'font_size': 10, 'align': 'vcenter', 'bold': True})        
        format2 = workbook.add_format({'font_size': 12, 'right': True, 'left': True, 'bottom': True, 'top': True, 'font_color':'white',
                                       'bg_color': '#288BA8', 'bold': True, 'valign': 'vcenter', 'align': 'center', 'text_wrap': False})
        format6 = workbook.add_format({'font_size': 10, 'align': 'left', 'bold': False, 'right': True, 'left': True,
                                       'bottom': True, 'top': True})
        format6R = workbook.add_format({'font_size': 10, 'align': 'left', 'bold': False, 'right': True, 'left': True,
                                       'bottom': True, 'top': True, 'align': 'right'})
        format6F = workbook.add_format({'font_size': 10, 'align': 'center', 'bold': False, 'right': True, 'left': True,
                                       'bottom': True, 'top': True, 'num_format':'dd/mm/yyyy'})        
        format7 = workbook.add_format({'font_size': 10, 'align': 'right', 'bold': False, 'right': True, 'left': True,
                                       'bottom': True, 'top': True, 'num_format': '#,##0'})
        format11 = workbook.add_format({'font_size': 12, 'align': 'center', 'bold': True})

        sheet.merge_range(0, 0, 0, 5, self.env.user.company_id.name, format0)
        sheet.merge_range(1, 1, 1, 3, 'Prestaciones sociales', format11)
        sheet.merge_range('A3:B3', 'Fecha liquidación: ' + data['date_stop'], format1)

        user = self.env['res.users'].browse(self.env.uid)
        tz = pytz.timezone(user.tz if user.tz else 'UTC')
        times = pytz.utc.localize(datetime.now()).astimezone(tz)
        sheet.merge_range('E3:F3', 'Fecha generación: ' + str(
            times.strftime("%Y-%m-%d %H:%M")), format1)

        sheet.set_row(0, 17)
        row = 3
        col = 0

        sheet.set_column(0, 0, 35)
        sheet.set_column(1, 1, 12)
        sheet.set_column(2, 2, 20)
        sheet.set_column(3, 3, 10)
        sheet.set_column(4, 4, 10)
        sheet.set_column(5, 5, 8)
        sheet.set_column(6, 6, 8)
        sheet.set_column(7, 7, 8)
        sheet.set_column(8, 8, 13)
        sheet.set_column(9, 9, 13)
        sheet.set_column(10, 10, 8)
        sheet.set_column(11, 11, 13)
        sheet.set_column(12, 12, 13)
        sheet.set_column(13, 13, 13)
        sheet.set_column(14, 14, 13)
        sheet.set_column(15, 15, 13)
        sheet.set_column(16, 16, 13)

        sheet.write(row, col,'Empleado', format2)
        sheet.write(row, col+1, 'Cédula', format2)
        sheet.write(row, col+2, "Concepto", format2)
        sheet.write(row, col+3, "F. inicial", format2)
        sheet.write(row, col+4, "F. final", format2)
        sheet.write(row, col+5, "Días", format2)
        sheet.write(row, col+6, "Sanción", format2)
        sheet.write(row, col+7, "Días neto", format2)
        sheet.write(row, col+8, "Salario básico", format2)
        sheet.write(row, col+9, "Salario variable", format2)
        sheet.write(row, col+10, "Días", format2)
        sheet.write(row, col+11, "Promedio", format2)
        sheet.write(row, col+12, "Subsidio t.", format2)
        sheet.write(row, col+13, "Base", format2)
        sheet.write(row, col+14, "Neto", format2)
        sheet.write(row, col+15, "Provisión", format2)
        sheet.write(row, col+16, "Ajuste", format2)

        row = 4
        col = 0
    
        consolidated = self.env['hr.liquidation.consolidated'].browse([data['id']])
        if consolidated:
           for line in consolidated.details_ids.sorted('employee_id'):

                sheet.write(row, col, line.employee_id.name, format6)
                sheet.write(row, col+1, line.employee_id.identification_id, format6)
                sheet.write(row, col+2, line.input_type_id.name, format6)
                sheet.write(row, col+3, line.date_from, format6F)
                sheet.write(row, col+4, line.date_to, format6F)
                sheet.write(row, col+5, line.days_total, format6R)
                sheet.write(row, col+6, line.days_leave, format6R)
                sheet.write(row, col+7, line.days_neto, format6R)
                sheet.write(row, col+8, line.wage_actual, format6R)
                sheet.write(row, col+9, line.wage_total, format6R)
                sheet.write(row, col+10, line.days_average, format6R)
                sheet.write(row, col+11, line.wage_average, format6R)
                sheet.write(row, col+12, line.subsidio_transporte, format6R)
                sheet.write(row, col+13, line.total_average, format6R)
                sheet.write(row, col+14, line.amount, format6R)
                sheet.write(row, col+15, line.provision, format6R)
                sheet.write(row, col+16, line.ajuste, format6R)
                
                row += 1

        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()

    def get_workbook_options(self):
        """
        See https://xlsxwriter.readthedocs.io/workbook.html constructor options
        :return: A dictionary of options
        """
        return {}



