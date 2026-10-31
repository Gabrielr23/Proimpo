# -*- coding: utf-8 -*-
"""Variantes del molde.

Un molde con varias piezas (por ejemplo cuchara, tenedor y cuchillo) se
puede correr con todas sus piezas o tapando cavidades para hacer solo
algunas. Cada combinación es una VARIANTE con su propio ciclo MEDIDO: al
tapar cavidades cambian la presión y el tiempo de inyección, así que el
ciclo no se puede calcular con una regla de tres.

La LdM elige la variante en su operación:
- LdM de una pieza (ST cuchara) → variante "Solo cuchara".
- LdM de juego (ST Juego cuchara + tenedor + cuchillo) → variante "Completa".
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MrpMoldVariant(models.Model):
    _name = 'mrp.mold.variant'
    _description = 'Variante del Molde'
    _inherit = ['mail.thread']
    _order = 'mold_id, sequence, id'
    _rec_names_search = ['complete_name', 'name']

    name = fields.Char(string='Variante', required=True, tracking=True,
                       help='Ej. "Completa", "Cuchara + tenedor", "Solo cuchara".')
    mold_id = fields.Many2one(
        'maintenance.equipment', string='Molde', required=True,
        ondelete='cascade', index=True, domain=[('is_mold', '=', True)])
    complete_name = fields.Char(
        string='Nombre Completo', compute='_compute_complete_name',
        store=True, index=True,
        help='"ML-000433 / Completa". Es el nombre que se usa para importar '
             'la variante en las operaciones, porque "Completa" se repite '
             'en muchos moldes.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    line_ids = fields.One2many(
        'mrp.mold.variant.line', 'variant_id', string='Piezas y Cavidades',
        copy=True)
    cycle_time = fields.Float(
        string='Ciclo Medido (seg)', digits=(10, 2), tracking=True,
        help='Segundos por disparo con ESTA combinación de cavidades '
             'abiertas. Se mide en la máquina; no se calcula.')
    cavity_total = fields.Integer(
        string='Cavidades Abiertas', compute='_compute_totals', store=True)
    sets_per_shot = fields.Integer(
        string='Juegos por Disparo', compute='_compute_totals', store=True,
        readonly=False,
        help='Para LdM de juego: cuántos juegos completos salen en un '
             'disparo. Por defecto, la menor cantidad de cavidades entre las '
             'piezas (2 cucharas + 2 tenedores → 2 juegos). Se puede cambiar.')
    pieces_summary = fields.Char(
        string='Piezas', compute='_compute_totals', store=True)
    shots_per_hour = fields.Float(
        string='Disparos por Hora', compute='_compute_shots_per_hour',
        digits=(10, 2))
    note = fields.Text(string='Observaciones')

    @api.depends('line_ids.cavities', 'line_ids.product_tmpl_id')
    def _compute_totals(self):
        for v in self:
            cavs = [l.cavities for l in v.line_ids if l.cavities > 0]
            v.cavity_total = sum(cavs)
            v.sets_per_shot = min(cavs) if cavs else 0
            v.pieces_summary = ', '.join(
                '%s ×%s' % (l.product_tmpl_id.name or '?', l.cavities)
                for l in v.line_ids)

    @api.depends('name', 'mold_id.mold_code', 'mold_id.name')
    def _compute_complete_name(self):
        for v in self:
            v.complete_name = '%s / %s' % (
                v.mold_id.mold_code or v.mold_id.name or '?', v.name or '')

    _sql_constraints = [
        ('name_mold_uniq', 'unique(mold_id, name)',
         'Ya existe una variante con ese nombre en este molde.'),
    ]

    @api.depends('cycle_time')
    def _compute_shots_per_hour(self):
        for v in self:
            v.shots_per_hour = 3600.0 / v.cycle_time if v.cycle_time else 0.0

    @api.constrains('line_ids', 'mold_id')
    def _check_cavities(self):
        for v in self:
            total = v.mold_id.cavity_count or 0
            if total and v.cavity_total > total:
                raise ValidationError(
                    'La variante "%s" abre %s cavidades, pero el molde %s '
                    'tiene %s.' % (v.name, v.cavity_total,
                                   v.mold_id.display_name, total))

    def units_per_shot(self, product_tmpl):
        """Unidades de `product_tmpl` que salen en un disparo.

        Si el producto es una de las piezas de la variante: sus cavidades.
        Si no (LdM de juego): los juegos por disparo.
        """
        self.ensure_one()
        linea = self.line_ids.filtered(
            lambda l: l.product_tmpl_id == product_tmpl)[:1]
        return linea.cavities if linea else self.sets_per_shot

    @api.depends('name', 'cycle_time')
    def _compute_display_name(self):
        for v in self:
            v.display_name = '%s (%s s)' % (v.name, ('%g' % v.cycle_time)
                                             if v.cycle_time else '?')


class MrpMoldVariantLine(models.Model):
    _name = 'mrp.mold.variant.line'
    _description = 'Pieza de una Variante del Molde'
    _order = 'variant_id, id'

    variant_id = fields.Many2one(
        'mrp.mold.variant', required=True, ondelete='cascade', index=True)
    product_tmpl_id = fields.Many2one(
        'product.template', string='Pieza', required=True,
        help='El semiterminado que sale de esas cavidades (ej. ST Cuchara '
             'NAVI).')
    cavities = fields.Integer(string='Cavidades', required=True, default=1)

    _sql_constraints = [
        ('cavities_positive', 'CHECK(cavities > 0)',
         'Las cavidades deben ser mayores que cero.'),
    ]
