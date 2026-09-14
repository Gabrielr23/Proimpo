# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'

    mold_id = fields.Many2one(
        'maintenance.equipment', string='Molde',
        domain="[('is_mold', '=', True), "
               "'|', ('compatible_workcenter_ids', '=', False), "
               "('compatible_workcenter_ids', '=', workcenter_id)]",
        context={"default_is_mold": True},
        help='Molde que ejecuta esta operación. Vínculo uno a uno. Al '
             'seleccionarlo se traen sus cavidades y ciclo, y la duración '
             'nativa de Odoo se recalcula a tiempo por UNA unidad. Si se '
             'deja vacío, la duración nativa no se toca. Si el molde no '
             'existe todavía, use "Crear y editar..." en este mismo campo: '
             'el nuevo registro nace marcado como molde, así que la pestaña '
             'de cavidades y ciclo aparece de inmediato.',
    )

    # --- Datos traídos del molde (solo lectura, para verlos sin abrir el molde) ---
    mold_cavity_count = fields.Integer(
        string='Cavidades', related='mold_id.cavity_count', readonly=True)
    mold_cycle_time = fields.Float(
        string='Ciclo del Molde (seg)', related='mold_id.cycle_time_effective',
        readonly=True, digits=(10, 2),
        help='Ciclo por disparo que usa el molde: su Ciclo Actual si está '
             'informado, y si no, su Ciclo Teórico.')
    mold_hourly_target = fields.Float(
        string='Objetivo por Hora (Molde)', related='mold_id.hourly_target',
        readonly=True, digits=(10, 2))

    hourly_target = fields.Float(
        string='Objetivo por Hora', compute='_compute_hourly_target',
        digits=(10, 2),
        help='Unidades esperadas por hora en esta operación. Si tiene molde, '
             'se calcula con su ciclo y cavidades; si no, con la duración '
             'por unidad de la operación. Así toda operación tiene objetivo, '
             'tenga molde o no.')

    @api.depends('mold_id', 'mold_id.cycle_time_effective',
                 'mold_id.cavity_count', 'time_cycle')
    def _compute_hourly_target(self):
        """Cadena de respaldo: molde primero, ciclo de la operación después.

        No todas las operaciones usan molde (empaque, alistamiento,
        impresión), pero todas necesitan un objetivo por hora para poder
        comparar avance real contra esperado.
        """
        for op in self:
            if op.mold_id and op.mold_id.hourly_target:
                op.hourly_target = op.mold_id.hourly_target
            elif op.time_cycle:
                # time_cycle son minutos por unidad
                op.hourly_target = 60.0 / op.time_cycle
            else:
                op.hourly_target = 0.0

    def _mold_minutes_per_unit(self):
        """Minutos por UNA unidad, según ciclo y cavidades del molde.

        El ciclo del molde es por disparo, y un disparo produce tantas
        piezas como cavidades activas tenga. La duración nativa de Odoo en
        esta operación se expresa por unidad, así que hay que dividir entre
        cavidades antes de convertir a minutos.
        """
        self.ensure_one()
        mold = self.mold_id
        if not mold or not mold.cycle_time_effective or not mold.cavity_count:
            return 0.0
        return (mold.cycle_time_effective / mold.cavity_count) / 60.0

    @api.onchange('mold_id')
    def _onchange_mold_id_set_native_duration(self):
        """Al elegir un molde, actualiza la duración nativa de Odoo.

        Si el molde está vacío NO se toca la duración nativa: se respeta el
        valor que el facilitador haya puesto a mano, tal como se acordó.
        """
        for op in self:
            if not op.mold_id:
                continue
            minutes = op._mold_minutes_per_unit()
            if minutes:
                op.time_mode = 'manual'
                op.time_cycle_manual = minutes
