# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import ormcache
from odoo.exceptions import UserError

class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'
    _description = 'Regla salarial'

    average_salary = fields.Boolean('Promedio salarial prima y cesantías', required=True, default=False)
    average_salary_vacation = fields.Boolean('Promedio salarial vacaciones', required=True, default=False)
    liquidation_type = fields.Selection([('N','No aplica'), 
                                         ('PV','Provisión vacaciones'),
                                         ('PC','Provisión cesantías'),
                                         ('PIC','Provisión intereses'),
                                         ('PP','Provisión prima')],
                                       'Tipo liquidación', required=True, default='N')

