# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'

    mold_id = fields.Many2one(
        'maintenance.equipment', string='Molde Principal',
        domain="[('is_mold', '=', True), ('is_enabled', '=', True), "
               "'|', ('compatible_workcenter_ids', '=', False), "
               "('compatible_workcenter_ids', '=', workcenter_id)]",
        context={"default_is_mold": True},
        help='Molde estándar de esta operación. Al seleccionarlo se traen '
             'sus cavidades y ciclo, y la duración nativa se recalcula a '
             'tiempo por UNA unidad. Si se deja vacío, la duración nativa '
             'no se toca.',
    )
    alternative_mold_ids = fields.Many2many(
        'maintenance.equipment',
        'mrp_routing_workcenter_alt_mold_rel',
        'operation_id', 'mold_id',
        string='Moldes Alternativos',
        domain="[('is_mold', '=', True), ('id', '!=', mold_id)]",
        help='Otros moldes que pueden ejecutar esta operación — típicamente '
             'el molde viejo cuando se compra uno nuevo. Es el equivalente '
             'a los centros de trabajo alternativos, pero para moldes. Cada '
             'uno conserva sus propias cavidades y ciclo.',
    )
    mold_has_variants = fields.Boolean(
        related='mold_id.has_variants', string='Molde con Variantes')
    mold_variant_id = fields.Many2one(
        'mrp.mold.variant', string='Variante del Molde',
        domain="[('mold_id', '=', mold_id)]",
        help='Qué combinación de cavidades usa esta LdM. Ej. la LdM de la '
             'cuchara usa "Solo cuchara"; la LdM del juego usa "Completa". '
             'El tiempo por unidad sale del ciclo medido de la variante.')
    all_mold_ids = fields.Many2many(
        'maintenance.equipment', string='Todos los Moldes Posibles',
        compute='_compute_all_mold_ids',
        help='Principal + alternativos. Es la lista que consulta la orden '
             'de trabajo y, en el futuro, el planificador.')

    @api.depends('mold_id', 'alternative_mold_ids')
    def _compute_all_mold_ids(self):
        for op in self:
            op.all_mold_ids = op.mold_id | op.alternative_mold_ids

    # --- Datos del molde principal, visibles sin abrir su ficha ---
    mold_cavity_count = fields.Integer(
        string='Cavidades del Molde', related='mold_id.cavity_count',
        readonly=True)
    mold_cycle_time = fields.Float(
        string='Ciclo del Molde (seg)', related='mold_id.cycle_time_effective',
        readonly=True, digits=(10, 2))
    mold_hourly_target = fields.Float(
        string='Objetivo por Hora (Molde)', related='mold_id.hourly_target',
        readonly=True, digits=(10, 2))

    hourly_target = fields.Float(
        string='Objetivo por Hora', compute='_compute_hourly_target',
        digits=(10, 2),
        help='Unidades esperadas por hora. Si hay molde, se calcula con su '
             'ciclo y cavidades; si no, con la duración por unidad de la '
             'operación. Así toda operación tiene objetivo, use molde o no.')

    @api.depends('mold_id', 'mold_id.cycle_time_effective',
                 'mold_id.cavity_count', 'mold_variant_id.cycle_time',
                 'mold_variant_id.line_ids.cavities',
                 'mold_variant_id.sets_per_shot', 'time_cycle')
    def _compute_hourly_target(self):
        for op in self:
            minutos = op._mold_minutes_per_unit() if op.mold_id else 0.0
            if minutos:
                op.hourly_target = 60.0 / minutos
            elif op.time_cycle:
                op.hourly_target = 60.0 / op.time_cycle
            else:
                op.hourly_target = 0.0

    def _mold_minutes_per_unit(self, mold=None):
        """Minutos por UNA unidad según ciclo y cavidades del molde.

        El ciclo es por disparo, y un disparo produce tantas piezas como
        cavidades activas, así que hay que dividir antes de convertir a
        minutos.
        """
        self.ensure_one()
        mold = mold or self.mold_id
        if not mold:
            return 0.0
        variante = self.mold_variant_id
        if variante and mold == self.mold_id and variante.mold_id == mold:
            unidades = variante.units_per_shot(self.bom_id.product_tmpl_id)
            if not variante.cycle_time or not unidades:
                return 0.0
            return (variante.cycle_time / unidades) / 60.0
        if not mold.cycle_time_effective or not mold.cavity_count:
            return 0.0
        return (mold.cycle_time_effective / mold.cavity_count) / 60.0

    @api.onchange('mold_id', 'mold_variant_id')
    def _onchange_mold_id_set_native_duration(self):
        """Al elegir molde, actualiza la duración nativa de Odoo.

        Si el molde queda vacío NO se toca la duración: se respeta el valor
        que el facilitador haya puesto a mano.
        """
        for op in self:
            if not op.mold_id:
                continue
            if op.mold_variant_id and op.mold_variant_id.mold_id != op.mold_id:
                op.mold_variant_id = False
            if op.mold_id.has_variants and not op.mold_variant_id:
                continue
            minutos = op._mold_minutes_per_unit()
            if minutos:
                op.time_mode = 'manual'
                op.time_cycle_manual = minutos

    # ------------------------------------------------------------------
    # La duración se calcula también AL GUARDAR, no solo al elegir el molde
    # en pantalla: así funciona igual a mano, por importación de Excel o por
    # cualquier otro camino.
    # ------------------------------------------------------------------
    _MOLD_DURATION_TRIGGERS = ('mold_id', 'mold_variant_id')

    def _apply_mold_cycle(self):
        for op in self:
            if not op.mold_id:
                continue
            if op.mold_id.has_variants and not op.mold_variant_id:
                continue
            minutos = op._mold_minutes_per_unit()
            if minutos and (op.time_mode != 'manual'
                            or abs((op.time_cycle_manual or 0) - minutos) > 1e-6):
                op.with_context(mold_cycle_applied=True).write({
                    'time_mode': 'manual',
                    'time_cycle_manual': minutos,
                })

    @api.model_create_multi
    def create(self, vals_list):
        ops = super().create(vals_list)
        if not self.env.context.get('mold_cycle_applied'):
            ops.filtered('mold_id')._apply_mold_cycle()
        return ops

    def write(self, vals):
        res = super().write(vals)
        if (not self.env.context.get('mold_cycle_applied')
                and any(k in vals for k in self._MOLD_DURATION_TRIGGERS)):
            self._apply_mold_cycle()
        return res
