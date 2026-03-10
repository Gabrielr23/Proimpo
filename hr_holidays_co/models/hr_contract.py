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

def proximafecha(fecha, periocidad):
    day = fecha.day
    month = fecha.month
    year = fecha.year
    if (month + periocidad) > 12:
        sobrante = (month + periocidad) - 12
        nextmonth = sobrante
        nextyear = year + 1
    elif month == 12 and periocidad == 1:
        nextmonth = 1
        nextyear = year + 1
    else:
        nextmonth = month + periocidad
        nextyear = year
    dia = fecha.day
    while dia >= 0:
        try:
            return datetime(nextyear, nextmonth, dia)
        except:
            dia -= 1

def dias360(fechai, fechaf):
    import calendar
    dias = 0
    sumar = 0
    entro = False
    sumar2 = False
    while fechai < fechaf:
        if sumar2:
            try:
                fechai = fechai + timedelta(days=3)
            except:
                fechai = fechai + timedelta(days=2)
            sumar2 = False
        if (fechaf - fechai).days >= 28:
            fecha = fechaf
            sumar = (fechaf - fechai).days
            if sumar > 30:
                sumar = 30
            if sumar == 28:
                sumar = 30
            entro = True
        else:
            entro = False
            sumar = (fechaf - fechai).days
            if fechai.month == 2 and fechaf.month != 2:
                if calendar.isleap(fechai.year) and fechai.day >= 28:
                    sumar += 1
                elif not calendar.isleap(fechai.year) and fechai.day < 28:
                    sumar += 2
            if sumar > 30:
                sumar = 30
        dias += sumar
        if fechai.month == 2 and fechai.day == 28 and not entro:
            break
        if fechai.month == 2 and fechai.day == 28:
            sumar2 = True
        fechai = proximafecha(fechai, 1).date()

    return dias

class hr_contract(models.Model):
    _name = 'hr.contract'
    _inherit = "hr.contract"
    _description = "Contratos"
    
    @api.model
    def days_between(self, start_date, end_date):
        #Add 1 day to end date to solve different last days of month
        #s1, e1 =  datetime.strptime(start_date,"%Y-%m-%d") , datetime.strptime(end_date,"%Y-%m-%d")  + timedelta(days=1)
        s1, e1 =  start_date , end_date + timedelta(days=1)
        #Convert to 360 days

        s360 = (s1.year * 12 + s1.month) * 30 + s1.day
        e360 = (e1.year * 12 + e1.month) * 30 + e1.day

        #Count days between the two 360 dates and return tuple (months, days)
        res = divmod(e360 - s360, 30)

        return ((res[0] * 30) + res[1]) or 0.00


    def compute_holidays_pending(self):
        # Calcula los días de vacaciones pendientes al día de hoy

        for contract in self:
            print('*** EMPLEADO: ',contract.employee_id.name)
            date_now = datetime.now().date()
            day_start = contract.date_start

            if contract.date_end:
                 day_end = contract.date_end
            else:
                 day_end = date_now

            #dias = self.env['hr.contract'].days_between(day_start, day_end)
            dias_totales = dias360(day_start, day_end)
            print('Días bruto: ',dias_totales)
            vacaciones_tomadas = 0
            sanciones = 0
            leave_ids_vc = self.env['hr.holidays.report'].sudo().search([('reason_leave','=','vacation'),
                                                                         ('contract_id','=',contract.id),
                                                                         ('date_to','<=',day_end)
                                                                        ])
            for vc in leave_ids_vc:
                print('-- Vacaciones tomadas --')
                if vc.state == 'validate':
                   print('Fecha: ',vc.date_from,' días: ',vc.number_of_days_real) 
                   vacaciones_tomadas += vc.number_of_days_real

                print('-- Fin Vacaciones tomadas --')   

            # Basca las vacaciones que esten en la fecha de corte
            leave_ids_vc_entre = self.env['hr.holidays.report'].sudo().search([('reason_leave','=','vacation'),
                                                                         ('contract_id','=',contract.id),
                                                                         ('date_from','<',day_end),
                                                                         ('date_to','>=',day_end)
                                                                        ])
            for vac in leave_ids_vc_entre:
                if vac.state == 'validate':
                   # Calcula cuantos días hábiles hay
                   f_desde = vac.date_from
                   f_hasta = day_end

                   # Determina si el empleado trabaja el sábado como hábil
                   sabado = contract.employee_id.sabado
                   diff_day = 0    
                   delta = timedelta(days=1)

                   while f_desde <= f_hasta:   
                     print('Fecha: ',f_desde)    
                     print('nombre dia semana ',f_desde.strftime('%A'))    
                     if (not sabado and f_desde.strftime('%A').lower() in ('saturday','sábado')):
                        print('El sábado no es día hábil')
                     elif (f_desde.strftime('%A').lower() in ('sunday','domingo')):              
                        print('Es un domingo')
                     else:                            
                        if self.env['hr.holidays.public'].is_public_holiday(f_desde):   
                           print('Es festivo')
                        else:   
                           diff_day = diff_day + 1
                      
                     f_desde += delta                   

                   print('Días adicionales: ',diff_day)
                   vacaciones_tomadas += diff_day    

            # Busca las sanciones y licencias no remuneradas
            leave_ids_sn = self.env['hr.holidays.report'].sudo().search([('reason_leave','=','sanction'),
                                                                         ('contract_id','=',contract.id),
                                                                         ('date_to','<=',day_end)
                                                                        ])        
            for sn in leave_ids_sn:
                if sn.state == 'validate':
                    sanciones += sn.number_of_days

            dias_neto = dias_totales - (sanciones * -1)
            print('Sanciones: ',sanciones)
            print('Dias neto: ',dias_neto)
            dias_vacaciones = round(float((dias_neto * 15.00) / 360.00),2)
            print('Dias vacaciones: ',dias_vacaciones)
            print('Vacaciones tomadas: ',vacaciones_tomadas)
            dias_pendientes = dias_vacaciones - vacaciones_tomadas
            print('Dias pendientes: ',dias_pendientes)

            contract.dias_vacaciones_pendientes = dias_pendientes
		
    def _calculo_vacaciones_tomadas(self):

        for contract in self:
            print('** EMPLEADO: ',contract.employee_id.name)
            date_now = datetime.now().date()
            day_start = contract.date_start

            if contract.date_end:
                 day_end = contract.date_end
            else:
                 day_end = date_now

            dias_totales = dias360(day_start, day_end)
            vacaciones_tomadas = 0
            leave_ids_vc = self.env['hr.holidays.report'].sudo().search([('reason_leave','=','vacation'),
                                                                         ('contract_id','=',contract.id),
                                                                         ('date_to','<=',day_end)
                                                                        ])
            for vc in leave_ids_vc:
                if vc.state == 'validate':
                   vacaciones_tomadas += vc.number_of_days_real 

            print('Vacaciones tomadas: ',vacaciones_tomadas)

            # Basca las vacaciones que esten en la fecha de corte
            leave_ids_vc_entre = self.env['hr.holidays.report'].sudo().search([('reason_leave','=','vacation'),
                                                                         ('contract_id','=',contract.id),
                                                                         ('date_from','<',day_end),
                                                                         ('date_to','>=',day_end)
                                                                        ])
            for vac in leave_ids_vc_entre:
                if vac.state == 'validate':
                   # Calcula cuantos días hábiles hay
                   f_desde = vac.date_from
                   f_hasta = day_end

                   # Determina si el empleado trabaja el sábado como hábil
                   sabado = contract.employee_id.sabado
                   diff_day = 0    
                   delta = timedelta(days=1)

                   while f_desde <= f_hasta:   
                     print('Fecha: ',f_desde)    
                     print('nombre dia semana ',f_desde.strftime('%A'))    
                     if (not sabado and f_desde.strftime('%A').lower() in ('saturday','sábado')):
                        print('El sábado no es día hábil')
                     elif (f_desde.strftime('%A').lower() in ('sunday','domingo')):              
                        print('Es un domingo')
                     else:                            
                        if self.env['hr.holidays.public'].is_public_holiday(f_desde):   
                           print('Es festivo')
                        else:   
                           diff_day = diff_day + 1
                      
                     f_desde += delta                   

                   print('Días adicionales: ',diff_day )
                   vacaciones_tomadas += diff_day  
                   print('Total acaciones tomadas: ',vacaciones_tomadas)  

            contract.vacaciones_tomadas = vacaciones_tomadas


    def _calculo_sanciones(self):

        for contract in self:
            vacas = 0
            for line in contract.leave_ids_sn:
                if line.state == 'validate' and line.holiday_status_id and line.holiday_status_id.reason_leave == 'sanction':
                   vacas += line.number_of_days

            vacas = vacas * -1
            contract.sanciones = vacas

    leave_ids_vc = fields.One2many('hr.holidays.report', 'contract_id', 'Vacaciones', readonly=True, domain=[('reason_leave','=','vacation')])
    leave_ids_sn = fields.One2many('hr.holidays.report', 'contract_id', 'Sanciones', readonly=True, domain=[('reason_leave','=','sanction')])
    dias_vacaciones_pendientes = fields.Float(compute= compute_holidays_pending, string='Vacaciones pendientes')
    vacaciones_tomadas = fields.Float(compute=_calculo_vacaciones_tomadas, string='Vacaciones aprobadas')
    sanciones = fields.Float(compute=_calculo_sanciones, string='Sanciones')
    contract_end_date = fields.Date(string='Fecha de finalización contrato fijo')
    

    def vacaciones_tomadas_pen(self, date_liquidacion):
        result = 0.0
        for contract in self:
            day_start = contract.date_start
            if date_liquidacion:
                day_end = date_liquidacion
            else:
                day_end = datetime.strptime(date_now,"%Y-%m-%d")

            dias = self.env['hr.contract'].days_between(day_start, day_end)
            vacaciones = 0
            sanciones = 0
            for vc in contract.leave_ids_vc:
                if vc.state == 'validate':
                    vacaciones += vc.number_of_days_real
            for sn in contract.leave_ids_sn:
                if sn.state == 'validate':
                    sanciones += sn.number_of_days
    
            dias = dias - (sanciones * -1)
            dias = float((dias * 15.00) / 360.00)
            dias = dias - (vacaciones)
            result = dias

        return dias

    def compute_holidays_pending2(self):

        res = {}

        for contract in self:

            date_now = datetime.now().strftime(DEFAULT_SERVER_DATE_FORMAT)
            day_start = datetime.strptime(contract.date_start,"%Y-%m-%d")
            day_end = datetime.strptime(date_now,"%Y-%m-%d")
            if date:
                day_end = datetime.strptime(date,"%Y-%m-%d")
            else:
                day_end = datetime.strptime(date_now,"%Y-%m-%d")
            
            #dias = days_between(day_start, day_end)
            dias = self.env['hr.contract'].days_between(day_start, day_end)

            vacaciones = 0
            sanciones = 0
            for vc in contract.leave_ids_vc:
                if vc.state == 'validate':
                    vacaciones += vc.number_of_days
            for sn in contract.leave_ids_sn:
                if sn.state == 'validate':
                    sanciones += sn.number_of_days

            dias = dias - (sanciones * -1)

            dias = float((dias * 15.00) / 360.00)

            dias = dias - (vacaciones * -1)

            res[contract.id] = dias

        return dias     
