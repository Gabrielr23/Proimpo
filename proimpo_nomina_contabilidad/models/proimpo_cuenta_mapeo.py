# -*- coding: utf-8 -*-
from odoo import models, fields
from .account_analytic_account import AREAS


class ProimpoCuentaMapeo(models.Model):
    _name = 'proimpo.cuenta.mapeo'
    _description = 'Mapeo de cuentas de nomina por area'
    _order = 'rule_code, area'

    rule_code = fields.Char(string="Codigo regla", required=True, index=True)
    rule_name = fields.Char(string="Nombre regla")
    area = fields.Selection(AREAS, string="Area", required=True)
    account_debit_id = fields.Many2one('account.account', string="Cuenta debito")
    account_credit_id = fields.Many2one('account.account', string="Cuenta credito")

    _sql_constraints = [
        ('uniq_rule_area', 'unique(rule_code, area)',
         'Ya existe un mapeo para esa regla y area.'),
    ]

    def aplicar_a_reglas(self):
        """Fija en cada regla salarial su cuenta por defecto (area Admin), para que
        Odoo genere las lineas del asiento; el override luego cambia la cuenta por area."""
        Rule = self.env['hr.salary.rule']
        n = 0
        for m in self.search([('area', '=', 'admin')]):
            rules = Rule.search([('code', '=', m.rule_code)])
            vals = {}
            if m.account_debit_id:
                vals['account_debit'] = m.account_debit_id.id
            if m.account_credit_id:
                vals['account_credit'] = m.account_credit_id.id
            if vals and rules:
                rules.write(vals)
                n += len(rules)
        return n
