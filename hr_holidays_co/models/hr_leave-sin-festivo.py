# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import DEFAULT_SERVER_DATE_FORMAT,DEFAULT_SERVER_DATETIME_FORMAT
import time
from datetime import date, datetime, timedelta
from dateutil import relativedelta, parser
import odoo.tools
from odoo.tools.translate import _
import odoo.netsvc

class HrLeave(models.Model):
    _name = 'hr.leave'
    _inherit = "hr.leave"
    _description = "Ausencias"

    @api.depends('employee_id', 'request_date_from')
    def _get_contract(self):
        for leave in self:
            if leave.request_date_from:
               leave.contract_id = leave.employee_id.get_contract(leave.request_date_from)

            if not leave.contract_id:
               raise ValidationError('No se encuentra un contrato activo para el empleado hlsf %s' % (leave.employee_id.name,))

    def _check_date_period(self):
        for holiday in self:
            if holiday.period_date_to:
               if holiday.period_date_to < holiday.period_date_from:
                  return False
        return True

    @api.model
    @api.depends('date_from','date_to','employee_id','holiday_status_id')
    def _compute_days_real(self):
        print('** _compute_days_real HABILES')           
        for line in self:
            diff_day = 0.0
            print('Desde: ',line.date_from)
            print('Hasta: ',line.date_to)
            
            #se calculan días hábilies solo si son vacaciones
            if (line.holiday_status_id and line.holiday_status_id.name.upper().find('VACACION') == -1) or not line.date_from or not line.date_to:
               line.number_of_days_real = 0
               continue

            f_desde = line.date_from.date()
            f_hasta = line.date_to.date()
                  
            # Determina si el empleado trabaja el sábado como hábil
            sabado = line.employee_id.sabado
            
            diff_day = 0    
            delta = timedelta(days=1)

            while f_desde <= f_hasta:       
              print('nombre dia semana ',f_desde.strftime('%A'))    
              if (not sabado and f_desde.strftime('%A').lower() in ('saturday','sábado')):
                 print('El sábado no es día hábil')
              elif (f_desde.strftime('%A').lower() in ('sunday','domingo')):              
                 print('Es un domingo')
              else:     
                 diff_day = diff_day + 1                       
                 #if self.env['hr.holidays.public'].is_public_holiday(f_desde):   
                 #   print('Es festivo')
                 #else:   
                 #   diff_day = diff_day + 1
                      
              f_desde += delta                   

            line.number_of_days_real = diff_day



    contract_id = fields.Many2one('hr.contract', compute = _get_contract, string="Contrato", store=True)
    approve_date = fields.Datetime('Fecha aprobacion', readonly=True)
    period_date_from = fields.Date('Fecha inicio periodo', copy=False)
    period_date_to = fields.Date('Fecha fin periodo', copy=False)
    number_of_days_real = fields.Float('Días hábiles', compute='_compute_days_real', default=0.0, readonly=True, store=True)
    reason_leave = fields.Selection([('vacation', 'Vacación'), 
                                     ('sanction', 'Sanción'), 
                                     ('other', 'Other')], 
                                     related='holiday_status_id.reason_leave', string='Motivo ausencia',
                                     help="Motivo de la ausencia")    

    

    _constraints = [
        (_check_date_period, 'La fecha inicial debe ser menor que la fecha mayor!', ['period_date_from','period_date_to']),
    ] 


    def _get_number_of_days_without_31(self, date_from, date_to):
        """"
          Cuenta días sin tener en cuenta el día 31
        """      
        diff_day = 0.0
        f_desde = date_from
        f_hasta = date_to   
        delta = timedelta(days=1)

        while f_desde <= f_hasta:       
            if f_desde.day != 31: 
               diff_day += 1
                      
            f_desde += delta        

        return diff_day

    
    def _get_number_of_days(self, date_from, date_to, employee_id):
        result = super(HrLeave, self)._get_number_of_days(date_from, date_to, employee_id)
        if result.get('days'):
           days = self._get_number_of_days_without_31(date_from, date_to) 
           result['days'] = days

        return result   


    def action_approve(self):
        for leave in self:
            leave.approve_date = fields.Datetime.now()

        return super(HrLeave, self).action_approve()


