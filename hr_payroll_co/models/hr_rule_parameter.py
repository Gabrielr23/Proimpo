# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval
import ast
from odoo.tools import ormcache

from odoo.addons import decimal_precision as dp

class HrRuleParameter(models.Model):
    _inherit = 'hr.rule.parameter'
    _description = 'Parámetros de reglas salariales'

    type = fields.Selection([('general','Genérico'), ('contrat','Por contrato')],'Nivel', required=True, default='general')
    data_type = fields.Selection([('T','Texto'), 
                                  ('N','Numérico'),
                                  ('B','Booleano'),
                                  ('F','Fecha'),
                                  ('C','Cuenta contable'),
                                  ('A','Asociado')],
                                  'Tipo dato', required=True, default='T')


