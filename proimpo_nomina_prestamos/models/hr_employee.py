# -*- coding: utf-8 -*-
from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    loan_ids = fields.One2many('hr.employee.loan', 'employee_id', string='Préstamos/Libranzas')
