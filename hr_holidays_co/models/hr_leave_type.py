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

class hr_leave_type(models.Model):
    _inherit = "hr.leave.type"
    _description = "Tipos de Ausencia"

    reason_leave = fields.Selection([('vacation', 'Vacación'), 
                                     ('sanction', 'Sanción y Licencia no remunerada'), 
                                     ('other', 'Other')], 
                                     required=True, default='other', string='Motivo ausencia',
                                     help="Motivo de la ausencia")    


