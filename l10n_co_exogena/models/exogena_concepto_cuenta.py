# -*- coding: utf-8 -*-
from odoo import models, fields


class ExogenaConceptoCuenta(models.Model):
    _name = 'exogena.concepto.cuenta'
    _description = 'Cuenta contable asociada a un concepto de exógena'

    concepto_id = fields.Many2one('exogena.concepto', 'Concepto',
                                  required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', 'Cuenta contable',
                                 required=True)
    valor = fields.Selection([
        ('debito', 'Movimiento débito'),
        ('credito', 'Movimiento crédito'),
        ('saldo', 'Saldo (débito - crédito)'),
        ('saldo_inv', 'Saldo (crédito - débito)'),
    ], string='Valor a tomar', default='debito', required=True,
        help='Débito: para pagos/costos/gastos. Crédito: para ingresos y '
             'retenciones practicadas. Saldo: para cuentas por cobrar. '
             'Saldo (crédito-débito): para cuentas por pagar.')
    company_id = fields.Many2one('res.company', 'Compañía',
                                 default=lambda self: self.env.company)
