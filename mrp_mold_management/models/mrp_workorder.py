# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    mold_id = fields.Many2one(
        'maintenance.equipment', string='Molde',
        domain="[('is_mold', '=', True), "
               "('compatible_workcenter_ids', '=', workcenter_id)]",
        help='Molde instalado para esta orden de trabajo. Solo se listan '
             'moldes marcados como compatibles con el centro de trabajo '
             'seleccionado arriba. Se asigna solo cuando hay un único molde '
             'candidato sin ambigüedad; si hay varios, queda en blanco para '
             'que el planeador decida.',
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
        """Asigna el molde solo. Nunca si hay ambigüedad.

        Candidato = molde activo, compatible con el centro de trabajo de la
        orden, y calificado para la LdM del producto en fabricación. Si hay
        exactamente un candidato, se asigna; si hay cero o varios, se deja en
        blanco para que el planeador decida (criterio humano: disponibilidad,
        fecha de entrega, o si el molde ya está montado).
        """
        Equipment = self.env['maintenance.equipment'].sudo()
        for wo in self:
            if wo.mold_id or not wo.workcenter_id:
                continue

            bom = wo.production_id.bom_id
            domain = [
                ('is_mold', '=', True),
                ('active', '=', True),
                ('compatible_workcenter_ids', '=', wo.workcenter_id.id),
            ]
            if bom:
                domain.append(('qualified_operation_ids.bom_id', '=', bom.id))

            candidatos = Equipment.search(domain)
            if len(candidatos) == 1:
                wo.mold_id = candidatos.id

    @api.model_create_multi
    def create(self, vals_list):
        workorders = super().create(vals_list)
        workorders._auto_assign_mold()
        return workorders
