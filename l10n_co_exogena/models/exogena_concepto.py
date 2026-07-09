# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ExogenaConcepto(models.Model):
    _name = 'exogena.concepto'
    _description = 'Concepto de Información Exógena DIAN'
    _order = 'formato_id, code'

    formato_id = fields.Many2one('exogena.formato', 'Formato',
                                 required=True, ondelete='cascade')
    code = fields.Char('Concepto', required=True,
                       help='Código DIAN del concepto, p. ej. 5004')
    name = fields.Char('Descripción', required=True)
    tipo = fields.Selection([
        ('pago_ded', 'Pago/abono deducible'),
        ('pago_no_ded', 'Pago/abono no deducible'),
        ('ret_renta', 'Retención en la fuente - renta'),
        ('ret_iva', 'Retención en la fuente - IVA'),
        ('ret_timbre', 'Retención en la fuente - timbre'),
        ('ingreso', 'Ingreso'),
        ('iva_desc', 'IVA descontable'),
        ('iva_gen', 'IVA generado / consumo'),
        ('saldo', 'Saldo (CxC / CxP)'),
        ('otro', 'Otro'),
    ], string='Tipo / columna', default='pago_ded', required=True,
        help='Define en qué columna del formato se acumula el valor.')
    cuenta_ids = fields.One2many('exogena.concepto.cuenta', 'concepto_id',
                                 'Cuentas contables asociadas')
    cuenta_count = fields.Integer('Cuentas', compute='_compute_cuenta_count')
    nota = fields.Char('Nota')

    @api.depends('cuenta_ids')
    def _compute_cuenta_count(self):
        for rec in self:
            rec.cuenta_count = len(rec.cuenta_ids)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code or ''} · {rec.name or ''}"
