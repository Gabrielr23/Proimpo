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
        string='Cavidades', related='mold_id.cavity_count', readonly=True)
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
                 'mold_id.cavity_count', 'time_cycle')
    def _compute_hourly_target(self):
        for op in self:
            if op.mold_id and op.mold_id.hourly_target:
                op.hourly_target = op.mold_id.hourly_target
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
        if not mold or not mold.cycle_time_effective or not mold.cavity_count:
            return 0.0
        return (mold.cycle_time_effective / mold.cavity_count) / 60.0

    @api.onchange('mold_id')
    def _onchange_mold_id_set_native_duration(self):
        """Al elegir molde, actualiza la duración nativa de Odoo.

        Si el molde queda vacío NO se toca la duración: se respeta el valor
        que el facilitador haya puesto a mano.
        """
        for op in self:
            if not op.mold_id:
                continue
            minutos = op._mold_minutes_per_unit()
            if minutos:
                op.time_mode = 'manual'
                op.time_cycle_manual = minutos
