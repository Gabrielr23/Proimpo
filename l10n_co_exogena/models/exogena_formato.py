# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ExogenaFormato(models.Model):
    _name = 'exogena.formato'
    _description = 'Formato de Información Exógena DIAN'
    _order = 'year desc, code'

    name = fields.Char('Nombre', required=True)
    code = fields.Char('Código', required=True, help='Código DIAN del formato, p. ej. 1001')
    version = fields.Char('Versión', help='Versión del formato, p. ej. 11')
    year = fields.Integer('Año gravable', required=True,
                          default=lambda self: fields.Date.today().year - 1)
    description = fields.Text('Descripción')
    concepto_ids = fields.One2many('exogena.concepto', 'formato_id', 'Conceptos')
    concepto_count = fields.Integer('N.º de conceptos', compute='_compute_concepto_count')
    active = fields.Boolean('Activo', default=True)

    _sql_constraints = [
        ('code_year_uniq', 'unique(code, year)',
         'Ya existe un formato con ese código para ese año gravable.'),
    ]

    @api.depends('concepto_ids')
    def _compute_concepto_count(self):
        for rec in self:
            rec.concepto_count = len(rec.concepto_ids)

    @api.depends('code', 'name', 'year')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code or ''} · {rec.name or ''} ({rec.year or ''})"
