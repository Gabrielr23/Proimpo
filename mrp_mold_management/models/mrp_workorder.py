# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    mold_id = fields.Many2one(
        'maintenance.equipment', string='Molde',
        domain="[('is_mold', '=', True), ('is_enabled', '=', True), "
               "'|', ('compatible_workcenter_ids', '=', False), "
               "('compatible_workcenter_ids', '=', workcenter_id)]",
        context={"default_is_mold": True},
        help='Molde con el que se ejecuta esta orden. Se asigna solo cuando '
             'no hay ambigüedad; si la operación tiene varios moldes '
             'posibles compatibles con el centro, la decisión es de quien '
             'planifica.',
    )
    mold_hourly_target = fields.Float(
        string='Objetivo por Hora (Molde)', related='mold_id.hourly_target',
        readonly=True, digits=(10, 2))

    hourly_target = fields.Float(
        string='Objetivo por Hora', compute='_compute_hourly_target',
        digits=(10, 2),
        help='Cadena de respaldo: molde, luego ciclo de la operación, luego '
             'duración esperada. Así toda orden tiene objetivo.')

    @api.depends('mold_id', 'mold_id.cycle_time_effective',
                 'mold_id.cavity_count', 'operation_id',
                 'operation_id.time_cycle', 'duration_expected',
                 'qty_production')
    def _compute_hourly_target(self):
        for wo in self:
            target = 0.0
            if wo.mold_id and wo.mold_id.hourly_target:
                target = wo.mold_id.hourly_target
            elif wo.operation_id and wo.operation_id.time_cycle:
                target = 60.0 / wo.operation_id.time_cycle
            elif wo.duration_expected and wo.qty_production:
                horas = wo.duration_expected / 60.0
                if horas:
                    target = wo.qty_production / horas
            wo.hourly_target = target

    mold_duration_expected = fields.Float(
        string='Duración Según Molde (min)',
        compute='_compute_mold_duration_expected', digits=(10, 2),
        help='Lo que debería durar esta orden con el ciclo y cavidades '
             'reales del molde asignado.')

    @api.depends('mold_id', 'mold_id.cycle_time_effective',
                 'mold_id.cavity_count', 'qty_producing', 'qty_production',
                 'workcenter_id.time_start', 'workcenter_id.time_stop')
    def _compute_mold_duration_expected(self):
        for wo in self:
            wo.mold_duration_expected = wo._mold_duration(wo.mold_id)

    def _mold_duration(self, mold):
        """Duración esperada en minutos usando un molde concreto."""
        self.ensure_one()
        if not mold or not mold.cycle_time_effective or not mold.cavity_count:
            return 0.0
        qty = self.qty_production or self.qty_producing or 0.0
        segundos_ud = mold.cycle_time_effective / mold.cavity_count
        produccion = (qty * segundos_ud) / 60.0
        wc = self.workcenter_id
        setup = (wc.time_start or 0.0) + (wc.time_stop or 0.0)
        return setup + produccion

    # ------------------------------------------------------------------
    # Conflicto de molde
    # ------------------------------------------------------------------
    mold_conflict = fields.Boolean(
        string='Molde en Conflicto', compute='_compute_mold_conflict',
        search='_search_mold_conflict',
        help='Otra orden de trabajo no terminada reclama el mismo molde en '
             'una ventana que se solapa con esta. Es un aviso, no un '
             'bloqueo: la decisión de cómo resolverlo es del planeador.')
    mold_conflict_info = fields.Char(
        string='Conflicto', compute='_compute_mold_conflict')

    @api.depends('mold_id', 'date_start', 'date_finished', 'state')
    def _compute_mold_conflict(self):
        for wo in self:
            conflicto = wo._find_mold_conflicts()
            wo.mold_conflict = bool(conflicto)
            wo.mold_conflict_info = (
                ', '.join(conflicto.mapped('display_name')[:3])
                if conflicto else False)

    @api.model
    def _search_mold_conflict(self, operator, value):
        """Permite filtrar por conflicto aunque el campo no esté almacenado.

        Se resuelve con una consulta directa que cruza órdenes del mismo
        molde con ventanas solapadas, en vez de calcular el campo registro
        por registro.
        """
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return []
        self.env.cr.execute("""
            SELECT DISTINCT a.id
            FROM mrp_workorder a
            JOIN mrp_workorder b
              ON a.mold_id = b.mold_id
             AND a.id <> b.id
            WHERE a.mold_id IS NOT NULL
              AND a.state NOT IN ('done', 'cancel')
              AND b.state NOT IN ('done', 'cancel')
              AND a.date_start IS NOT NULL
              AND a.date_finished IS NOT NULL
              AND b.date_start IS NOT NULL
              AND b.date_finished IS NOT NULL
              AND a.date_start < b.date_finished
              AND b.date_start < a.date_finished
        """)
        ids = [r[0] for r in self.env.cr.fetchall()]
        en_conflicto = (operator == '=') == bool(value)
        return [('id', 'in' if en_conflicto else 'not in', ids)]

    def _find_mold_conflicts(self):
        self.ensure_one()
        vacio = self.env['mrp.workorder']
        if not (self.mold_id and self.date_start and self.date_finished):
            return vacio
        if self.state in ('done', 'cancel'):
            return vacio
        return self.mold_id._overlapping_workorders(
            self.date_start, self.date_finished, exclude=self)

    # ------------------------------------------------------------------
    # Asignación automática — SOLO para el caso sin ambigüedad
    # ------------------------------------------------------------------
    def _auto_assign_mold(self):
        """Asigna el molde cuando no hay nada que decidir.

        Deliberadamente NO es planificación. Elegir entre varios moldes
        posibles optimizando fecha de entrega, dependencias entre
        operaciones y carga de los centros requiere ver todas las órdenes
        a la vez: eso es un planificador, un módulo aparte. Aquí solo se
        rellena el caso en que existe una única opción válida, para que el
        campo no quede vacío sin motivo.

        Si quedan varias candidatas, se deja vacío a propósito para que la
        decisión sea visible y la tome quien planifica.
        """
        for wo in self:
            if wo.mold_id or not wo.operation_id:
                continue
            candidatos = wo.operation_id.all_mold_ids.filtered(
                lambda m: m.is_enabled
                and m.mold_situation not in ('baja', 'reparacion'))
            if wo.workcenter_id:
                candidatos = candidatos.filtered(
                    lambda m: not m.compatible_workcenter_ids
                    or wo.workcenter_id in m.compatible_workcenter_ids)
            if len(candidatos) == 1:
                wo.mold_id = candidatos.id
                wo._apply_mold_duration()

    def _apply_mold_duration(self):
        """Alinea la duración esperada con el molde asignado.

        Se hace al crear la orden —no durante la ejecución— porque es el
        momento en que Odoo calcula `duration_expected` con el ciclo
        estático de la ruta y todavía nadie ha planificado encima.
        """
        for wo in self:
            minutos = wo._mold_duration(wo.mold_id)
            if minutos:
                wo.duration_expected = minutos

    def action_apply_mold_duration(self):
        """Recalcula la duración con el molde actual, bajo demanda."""
        self._apply_mold_duration()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Duración actualizada',
                'message': 'Se recalculó con el ciclo y cavidades del molde.',
                'type': 'success',
                'sticky': False,
            },
        }

    @api.onchange('workcenter_id')
    def _onchange_workcenter_id_clear_incompatible_mold(self):
        """Si cambia el centro y el molde ya no cabe, se limpia en vez de
        dejar una combinación imposible sin avisar."""
        for wo in self:
            if (wo.mold_id and wo.workcenter_id
                    and wo.mold_id.compatible_workcenter_ids
                    and wo.workcenter_id not in wo.mold_id.compatible_workcenter_ids):
                wo.mold_id = False

    @api.model_create_multi
    def create(self, vals_list):
        workorders = super().create(vals_list)
        workorders._auto_assign_mold()
        return workorders
