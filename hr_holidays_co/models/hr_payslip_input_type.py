# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import ormcache
from odoo.exceptions import UserError

class HrPayslipInputType(models.Model):
    _inherit = 'hr.payslip.input.type'
    _description = 'Otros parámetros de regla'

    liquidation_type = fields.Selection([('N','No aplica'), 
                                         ('V','Vacaciones'),
                                         ('C','Cesantías'),
                                         ('IC','Intereses de cesantías'),
                                         ('P','Prima'),
                                         ('PV','Provisión vacaciones'),
                                         ('PC','Provisión cesantías'),
                                         ('PIC','Provisión Intereses'),
                                         ('PP','Provisión prima'),
                                         ('I','Indemnización')],
                                       'Tipo liquidación', required=True, default='N')

