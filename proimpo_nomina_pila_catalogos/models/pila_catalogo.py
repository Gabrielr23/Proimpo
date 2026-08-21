# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PilaEntidad(models.Model):
    _name = 'pila.entidad'
    _description = 'Entidad PILA (EPS, AFP, ARL, Caja)'
    _order = 'tipo, name'

    tipo = fields.Selection([
        ('eps', 'EPS (salud)'),
        ('afp', 'AFP (pensión)'),
        ('arl', 'ARL'),
        ('ccf', 'Caja de compensación'),
    ], string='Tipo', required=True, index=True)
    code = fields.Char(string='Código operador', required=True)
    name = fields.Char(string='Nombre', required=True)
    nit = fields.Char(string='NIT')
    active = fields.Boolean(default=True)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s (%s)' % (r.name or '', r.code or '')

    @api.model
    def _search_display_name(self, operator, value):
        return ['|', ('name', operator, value), ('code', operator, value)]


class PilaMunicipio(models.Model):
    _name = 'pila.municipio'
    _description = 'Municipio DANE (PILA)'
    _order = 'name'

    code = fields.Char(string='Código DANE', required=True)
    name = fields.Char(string='Municipio', required=True)
    depto = fields.Char(string='Departamento')
    active = fields.Boolean(default=True)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s (%s)' % (r.name or '', r.code or '')

    @api.model
    def _search_display_name(self, operator, value):
        return ['|', ('name', operator, value), ('code', operator, value)]


class PilaArlClase(models.Model):
    _name = 'pila.arl.clase'
    _description = 'Clase de riesgo / centro de trabajo ARL'
    _order = 'code'

    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Descripción', required=True)
    tarifa = fields.Float(string='Tarifa', digits=(6, 5))

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s - %s' % (r.code or '', r.name or '')
