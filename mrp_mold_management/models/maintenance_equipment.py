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
    qualified_operation_ids = fields.One2many(
        'mrp.routing.workcenter', 'mold_id',
        string='Operaciones que Usan este Molde',
        help='Informativo, uno a uno: cada operación listada aquí tiene a '
             'este molde asignado directamente en su ficha de LdM. Para '
             'vincular o desvincular, edite el campo "Molde" en la '
             'operación, no aquí.',
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

    # ------------------------------------------------------------------
    # Propagación a la LdM: corrige la FUENTE, no cada orden individual
    # ------------------------------------------------------------------
    PUSH_PARAM = 'mrp_mold_management.push_cycle_to_routing'

    def _push_cycle_to_routing(self):
        """Escribe el ciclo vigente del molde en la(s) operación(es) de ruta
        vinculadas, para que TODA orden de trabajo creada de aquí en adelante
        nazca con el tiempo correcto, sin depender de que alguien la corrija
        a mano una por una.

        Se apaga con el parámetro de sistema `mrp_mold_management
        .push_cycle_to_routing` (por defecto activo). Apáguelo el día que
        el ajuste de LdM pase a gestionarse por PLM, para que este mecanismo
        no escriba por debajo de ese flujo de aprobación.

        Devuelve un resumen para que quien aplicó el cambio sepa exactamente
        qué se actualizó, qué se omitió por estar en modo automático (Odoo
        recalcula ese tiempo solo y este valor no tendría efecto), y qué
        molde no tiene ninguna operación vinculada todavía.
        """
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            self.PUSH_PARAM, 'True')
        if str(enabled).lower() not in ('1', 'true'):
            return {'updated': [], 'skipped_auto': [], 'unlinked': []}

        updated, skipped_auto, unlinked = [], [], []

        for mold in self:
            if not mold.cycle_time_current or not mold.cavity_count:
                continue

            minutes_per_unit = (mold.cycle_time_current / mold.cavity_count) / 60.0

            if not mold.qualified_operation_ids:
                unlinked.append(mold.display_name)
                continue

            for op in mold.qualified_operation_ids:
                etiqueta = '%s (%s)' % (op.name, op.bom_id.display_name or '')
                if op.time_mode != 'manual':
                    skipped_auto.append(etiqueta)
                    continue
                op.sudo().write({'time_cycle_manual': minutes_per_unit})
                updated.append(etiqueta)

        return {'updated': updated, 'skipped_auto': skipped_auto, 'unlinked': unlinked}
