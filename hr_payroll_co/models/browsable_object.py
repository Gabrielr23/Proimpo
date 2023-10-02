#-*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import fields

class BrowsableObject(object):
    def __init__(self, employee_id, dict, env):
        self.employee_id = employee_id
        self.dict = dict
        self.env = env

    def __getattr__(self, attr):
        return attr in self.dict and self.dict.__getitem__(attr) or 0.0

    def __getitem__(self, key):
        return self.dict[key] or 0.0
        
class Payslips(BrowsableObject):
    """a class that will be used into the python code, mainly for usability purposes"""

    def sum(self, code, from_date, to_date=None):
        if to_date is None:
            to_date = fields.Date.today()
        self.env.cr.execute("""
            SELECT sum(pl.total)
            FROM hr_payslip as hp, hr_payslip_line as pl
            WHERE hp.employee_id = %s
            AND hp.state = 'done'
            AND hp.date_from >= %s
            AND hp.date_to <= %s
            AND hp.id = pl.slip_id
            AND pl.code = %s""", (self.employee_id, from_date, to_date, code))
        res = self.env.cr.fetchone()
        return res and res[0] or 0.0

    def rule_parameter(self, code):
        return self.env['hr.rule.parameter']._get_parameter_from_code(code, self.dict.date_to)

    def sum_category(self, code, from_date, to_date=None):
        print('** sum_category')
        if to_date is None:
            to_date = fields.Date.today()

        self.env['hr.payslip'].flush(['employee_id', 'state', 'date_from', 'date_to'])
        self.env['hr.payslip.line'].flush(['total', 'slip_id', 'category_id'])
        self.env['hr.salary.rule.category'].flush(['code'])

        self.env.cr.execute("""
            SELECT sum(pl.total)
            FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule_category as rc
            WHERE hp.employee_id = %s
            AND hp.state = 'done'
            AND hp.date_from >= %s
            AND hp.date_to <= %s
            AND hp.id = pl.slip_id
            AND rc.id = pl.category_id
            AND rc.code = %s""", (self.employee_id, from_date, to_date, code))
        res = self.env.cr.fetchone()
        return res and res[0] or 0.0

    def sum_worked_days(self, code, from_date, to_date=None):
        if to_date is None:
            to_date = fields.Date.today()

        query = """
            SELECT sum(hwd.number_of_days)
            FROM hr_payslip hp, hr_payslip_worked_days hwd, hr_work_entry_type hwet
            WHERE hp.state in ('done','paid')
            AND hp.id = hwd.payslip_id
            AND hwet.id = hwd.work_entry_type_id
            AND hp.employee_id = %(employee)s
            AND hp.date_to <= %(stop)s
            AND hwet.code = %(code)s
            AND hp.date_from >= %(start)s"""

        self.env.cr.execute(query, {
            'employee': self.employee_id,
            'code': code,
            'start': from_date,
            'stop': to_date})
        res = self.env.cr.fetchone()
        print('res ',res)
        return res[0] if res and res[0] != None else 0.0

    @property
    def paid_amount(self):
        return self.dict._get_paid_amount()

    @property
    def is_outside_contract(self):
        return self.dict._is_outside_contract_dates()
