# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    # ------------------------------------------------------------------
    # Identificación
    # ------------------------------------------------------------------
    is_mold = fields.Boolean(
        string='Es un Molde',
        help='Marca este equipo como molde de inyección. Habilita los campos '
             'de cavidades, ciclo y compatibilidad con centros de trabajo.',
    )

    # ------------------------------------------------------------------
    # Especificaciones de producción (cambian por desgaste/mantenimiento)
    # ------------------------------------------------------------------
    cavity_count = fields.Integer(
        string='Cavidades Actuales', default=1,
        help='Número de cavidades activas hoy. Se actualiza tras una '
             'revisión que confirme un cambio (ver Bitácora de Revisión).',
    )
    cycle_time_theoretical = fields.Float(
        string='Ciclo Teórico (seg)', digits=(10, 2),
        help='Ciclo de referencia original del molde, en segundos por disparo. '
             'Rara vez cambia.',
    )
    cycle_time_current = fields.Float(
        string='Ciclo Actual (seg)', digits=(10, 2),
        help='Ciclo real vigente, en segundos por disparo. Se actualiza tras '
             'una revisión que confirme un cambio.',
    )
    standard_weight_g = fields.Float(
        string='Peso Estándar Pieza (g)', digits=(10, 2),
        help='Peso de referencia por pieza, incluyendo el margen de tolerancia '
             'acordado (p. ej. 3%).',
    )
    mold_weight_kg = fields.Float(string='Peso del Molde (kg)', digits=(10, 2))
    setup_hours = fields.Float(string='Setup Estimado (horas)', digits=(6, 2))

    # ------------------------------------------------------------------
    # Compatibilidad y calificación
    # ------------------------------------------------------------------
    compatible_workcenter_ids = fields.Many2many(
        'mrp.workcenter',
        'maintenance_equipment_mold_workcenter_rel',
        'equipment_id', 'workcenter_id',
        string='Centros de Trabajo Compatibles',
        help='Centros de trabajo donde este molde puede montarse. Sin orden '
             'de prioridad: el planeador decide según disponibilidad y fecha '
             'de entrega.',
    )
    qualified_bom_ids = fields.Many2many(
        'mrp.bom',
        'maintenance_equipment_mold_bom_rel',
        'equipment_id', 'bom_id',
        string='LdM Calificadas',
        help='Listas de materiales que este molde está calificado para producir.',
    )

    # ------------------------------------------------------------------
    # Objetivo de producción (para el tablero de la Fase 1)
    # ------------------------------------------------------------------
    hourly_target = fields.Float(
        string='Objetivo por Hora', compute='_compute_hourly_target',
        digits=(10, 2),
        help='Piezas esperadas por hora con el ciclo y cavidades vigentes: '
             '3600 / (ciclo actual / cavidades). Se recalcula en vivo, así que '
             'refleja cualquier ajuste por desgaste sin intervención manual.',
    )

    @api.depends('cycle_time_current', 'cavity_count')
    def _compute_hourly_target(self):
        for eq in self:
            if eq.cycle_time_current and eq.cavity_count:
                eq.hourly_target = 3600.0 / (eq.cycle_time_current / eq.cavity_count)
            else:
                eq.hourly_target = 0.0

    # ------------------------------------------------------------------
    # Bitácora de revisión
    # ------------------------------------------------------------------
    revision_log_ids = fields.One2many(
        'mrp.mold.revision.log', 'equipment_id', string='Bitácora de Revisión')
    revision_count = fields.Integer(
        string='# Revisiones', compute='_compute_revision_count')

    @api.depends('revision_log_ids')
    def _compute_revision_count(self):
        for eq in self:
            eq.revision_count = len(eq.revision_log_ids)

    def action_view_revisions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bitácora de Revisión — %s' % self.name,
            'res_model': 'mrp.mold.revision.log',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': {'default_equipment_id': self.id},
        }
