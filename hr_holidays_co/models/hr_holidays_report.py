# -*- coding: utf-8 -*-

from odoo import tools
from odoo import api, fields, models, _
#from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

class hr_holidays_report(models.Model):

    _name = 'hr.holidays.report'
    _description = 'Total holidays by type vacation'
    _auto = False
    _order = 'date_from desc'

    name = fields.Char('Concepto')
    employee = fields.Char('Empleado')
    number_of_days = fields.Float('Días calendario')
    number_of_days_real = fields.Float('Días hábiles')
    approve_date = fields.Date('Fecha aprobación')
    date_from = fields.Date('Fecha desde')
    date_to = fields.Date('Fecha hasta')
    state = fields.Selection([('draft', 'To Submit'), ('cancel', 'Cancelled'),('confirm', 'To Approve'), ('refuse', 'Refused'), ('validate1', 'Second Approval'), ('validate', 'Approved')],
            'Estado', readonly=True, track_visibility='onchange', copy=False,
            help='Reporte para libro de vacaciones')
    contract_id = fields.Many2one('hr.contract', 'Contrato')
    holiday_status_id = fields.Many2one('hr.leave.type', 'Tipo ausencia')
    reason_leave = fields.Selection([('vacation', 'Vacación'), 
                                     ('sanction', 'Sanción'), 
                                     ('other', 'Other')], 
                                     required=True, default='other', string='Motivo ausencia',
                                     help="Motivo de la ausencia")    

    def init(self):
        tools.drop_view_if_exists(self.env.cr,'hr_holidays_report')
        self.env.cr.execute(""" 
                        create or replace view hr_holidays_report as (
                          select min(hrs.id) as id, 
                                 hhs.name->>'es_CO' as name, 
                                 rr.name as employee, 
                                 hrs.number_of_days as number_of_days, 
                                 hrs.number_of_days_real as number_of_days_real, 
                                 hrs.date_from::date as date_from, 
                                 hrs.date_to::date as date_to, 
                                 hrs.state as state, 
                                 hrs.contract_id as contract_id, 
                                 hrs.holiday_status_id as holiday_status_id, 
                                 hrs.approve_date as approve_date,
                                 hhs.reason_leave
                          from 
                                 hr_leave as hrs, hr_employee as hre, resource_resource as rr,hr_leave_type as hhs
                          where
                                 hrs.employee_id = hre.id 
                          and 
                                 hre.resource_id =  rr.id 
                          and 
                                 hhs.id = hrs.holiday_status_id 
                          and 
                                 hhs.reason_leave <> 'other'
                          group by
                                 rr.name,rr.user_id,hhs.name, hrs.date_from, hrs.date_to, hrs.state, hrs.number_of_days, 
                                 hrs.number_of_days_real, hrs.contract_id, hrs.holiday_status_id, hrs.approve_date, hhs.reason_leave
                          order by date_from desc       
                    )""")


