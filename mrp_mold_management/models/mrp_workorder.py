# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    mold_id = fields.Many2one(
        'maintenance.equipment', string='Molde',
        domain="[('is_mold', '=', True), "
               "'|', ('compatible_workcenter_ids', '=', False), "
               "('compatible_workcenter_ids', '=', workcenter_id)]",
        context={"default_is_mold": True},
        help='Molde instalado para esta orden de trabajo. Se copia solo '
             'desde el molde definido en la operación de la LdM de origen. '
             'Editable a mano si esta ejecución usa un molde distinto al '
             'estándar (por ejemplo, un respaldo mientras el habitual está '
             'en mantenimiento).',
    )
    mold_hourly_target = fields.Float(
        string='Objetivo por Hora (Molde)', related='mold_id.hourly_target',
        readonly=True, digits=(10, 2),
        help='Objetivo teórico de piezas por hora, según el ciclo y las '
             'cavidades vigentes del molde seleccionado.',
    )
    mold_duration_expected = fields.Float(
        string='Duración Según Molde (min)', compute='_compute_mold_duration_expected',
        digits=(10, 2),
        help='Lo que debería durar esta orden usando el ciclo y cavidades '
             'REALES del molde asignado, para comparar contra "Duración '
             'esperada" (que Odoo calculó con el ciclo estático de la ruta '
             'al crear la orden, y no se actualiza sola si el molde cambia). '
             'Use el botón "Aplicar duración del molde" para corregirla.',
    )

    @api.depends('mold_id', 'mold_id.cycle_time_current', 'mold_id.cavity_count',
                 'qty_producing', 'qty_production',
                 'workcenter_id.time_start', 'workcenter_id.time_stop')
    def _compute_mold_duration_expected(self):
        for wo in self:
            mold = wo.mold_id
            if not mold or not mold.cycle_time_current or not mold.cavity_count:
                wo.mold_duration_expected = 0.0
                continue

            qty = wo.qty_production or wo.qty_producing or 0.0
            seconds_per_unit = mold.cycle_time_current / mold.cavity_count
            production_minutes = (qty * seconds_per_unit) / 60.0

            wc = wo.workcenter_id
            setup_minutes = (wc.time_start or 0.0) + (wc.time_stop or 0.0)

            wo.mold_duration_expected = setup_minutes + production_minutes

    def action_apply_mold_duration(self):
        """Sobrescribe 'Duración esperada' con el cálculo real del molde.

        Deliberadamente manual (no automático): duration_expected alimenta
        el Gantt y las fechas comprometidas de la MO. Un cambio silencioso
        ahí es más riesgoso que un cambio silencioso en un campo informativo,
        así que el planeador confirma con este botón en lugar de que ocurra
        solo al cambiar el molde.
        """
        for wo in self:
            if wo.mold_duration_expected:
                wo.duration_expected = wo.mold_duration_expected
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Duración actualizada',
                'message': 'La duración esperada se recalculó con los datos del molde.',
                'type': 'success',
                'sticky': False,
            },
        }

    @api.onchange('workcenter_id')
    def _onchange_workcenter_id_clear_incompatible_mold(self):
        """Si cambia el centro de trabajo y el molde ya no es compatible,
        se limpia en lugar de dejar una combinación inválida sin avisar."""
        for wo in self:
            if wo.mold_id and wo.workcenter_id \
                    and wo.workcenter_id not in wo.mold_id.compatible_workcenter_ids:
                wo.mold_id = False

    def _auto_assign_mold(self):
        """Copia el molde directo desde la operación de origen.

        Ya no hay que buscar candidatos ni resolver ambigüedad: como el
        vínculo molde↔operación es uno a uno (se define en la LdM, en el
        campo "Molde" de cada operación), cada orden de trabajo sabe
        exactamente de qué operación viene (`operation_id`) y esa operación
        sabe exactamente qué molde le corresponde. Si `operation_id` no
        tiene molde asignado (o la orden no viene de una operación de LdM,
        por ejemplo un paso agregado a mano), queda en blanco para que el
        planeador lo asigne manualmente.
        """
        for wo in self:
            if not wo.mold_id and wo.operation_id and wo.operation_id.mold_id:
                wo.mold_id = wo.operation_id.mold_id

    @api.model_create_multi
    def create(self, vals_list):
        workorders = super().create(vals_list)
        workorders._auto_assign_mold()
        return workorders
