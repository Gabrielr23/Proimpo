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

class hr_employee(models.Model):
    
   _name = 'hr.employee' 
   _inherit = "hr.employee"
   _description = "Empleados"

   @api.model
   def get_contract(self, date_from):
       clause_final = [('employee_id', '=', self.id), ('date_start', '<=', date_from), '|', ('date_end', '=', False), ('date_end', '>=', date_from)]
       contract_ids = self.env['hr.contract'].sudo().search(clause_final)
       contract_ids
       if contract_ids:
          return contract_ids[0].id	
       else:   
          return False


   sabado = fields.Boolean('Sábado día hábil', required=True, default=True, help="Indica si el día sábado se incluye como día hábil")  


class HrEmployeePublic(models.Model):
    
   _inherit = "hr.employee.public"
   _description = "Empleados públicos"

   sabado = fields.Boolean('Sábado día hábil', required=True, default=True, help="Indica si el día sábado se incluye como día hábil")  
