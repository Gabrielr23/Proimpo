# -*- coding: utf-8 -*-
import logging

from odoo import fields, models, tools

_logger = logging.getLogger(__name__)


class MrpOeeReport(models.Model):
    _name = 'mrp.oee.report'
    _description = 'OEE por Turno'
    _auto = False
    _rec_name = 'shift_name'
    _order = 'shift_date desc, workcenter_id, shift_name'

    # ------------------------------------------------------------------
    # Dimensiones
    # ------------------------------------------------------------------
    shift_date = fields.Date(
        string='Fecha Operativa', readonly=True,
        help='Día en que arrancó el turno. Una línea de las 02:00 del '
             'martes que pertenece a "Lunes Turno 3" cuenta para el lunes.')
    shift_name = fields.Char(string='Turno', readonly=True)
    shift_is_planned = fields.Boolean(
        string='Turno Planeado', readonly=True,
        help='False si la franja tiene capacidad apagada (day_period '
             '"lunch"). La producción real se reporta igual, pero sin '
             'objetivo: es turno extra / no planeado.')
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Centro de Trabajo', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)

    # ------------------------------------------------------------------
    # Medidas base (sumables)
    # ------------------------------------------------------------------
    minutos_total = fields.Float(
        string='Minutos Totales', readonly=True, digits=(16, 2),
        help='Suma de la duración de todas las líneas de seguimiento de '
             'tiempo del turno, sin importar el motivo.')
    minutos_productivos = fields.Float(
        string='Minutos Productivos', readonly=True, digits=(16, 2),
        help='Solo las líneas cuyo motivo de pérdida es de tipo productivo.')
    unidades_buenas = fields.Integer(string='Unidades Buenas', readonly=True)
    unidades_averias = fields.Integer(string='Averías', readonly=True)
    unidades_teoricas = fields.Float(
        string='Unidades Teóricas', readonly=True, digits=(16, 2),
        help='Lo que se debería haber producido en los minutos productivos, '
             'según el objetivo por hora de cada línea (molde si lo hay, si '
             'no el ciclo manual de la operación).')

    # ------------------------------------------------------------------
    # Indicadores (calculados por fila en SQL, escala 0-100)
    # ------------------------------------------------------------------
    disponibilidad = fields.Float(
        string='Disponibilidad %', readonly=True, digits=(16, 2),
        help='Minutos productivos / minutos totales.')
    rendimiento = fields.Float(
        string='Rendimiento %', readonly=True, digits=(16, 2),
        help='Producción real (buenas + averías) / unidades teóricas.')
    calidad = fields.Float(
        string='Calidad %', readonly=True, digits=(16, 2),
        help='Unidades buenas / producción real.')
    oee = fields.Float(
        string='OEE %', readonly=True, digits=(16, 2),
        help='Disponibilidad × Rendimiento × Calidad.')

    # ------------------------------------------------------------------
    # Introspección: qué columnas existen realmente en esta base
    # ------------------------------------------------------------------
    def _column_exists(self, table, column):
        self.env.cr.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s", (table, column))
        return bool(self.env.cr.fetchone())

    def _build_query(self):
        """Construye el SQL adaptándose a las columnas disponibles.

        Solo se pueden leer columnas ALMACENADAS. Confirmado por
        diagnóstico en la instancia real:
          - qty_production (mrp.workorder) es store=False -> inutilizable
          - time_cycle (mrp.routing.workcenter) es store=False -> se usa
            time_cycle_manual, que sí está almacenado
          - cycle_time_effective (maintenance.equipment) está almacenado
        """
        P = 'mrp_workcenter_productivity'

        # shift_is_planned puede no existir si el módulo de turnos está en
        # una versión anterior: en ese caso se asume planeado.
        if self._column_exists(P, 'shift_is_planned'):
            planned_expr = 'BOOL_OR(p.shift_is_planned)'
            planned_line = 'p.shift_is_planned'
        else:
            planned_expr = 'TRUE'
            planned_line = 'TRUE'
            _logger.warning(
                '%s.shift_is_planned no existe: se asume que todos los '
                'turnos son planeados. Actualice mrp_shift_resolver.', P)

        # Ciclo efectivo del molde: se prefiere la columna almacenada; si
        # no existe, se replica su lógica de respaldo en SQL.
        if self._column_exists('maintenance_equipment', 'cycle_time_effective'):
            ciclo = 'NULLIF(eq.cycle_time_effective, 0)'
        else:
            ciclo = ('COALESCE(NULLIF(eq.cycle_time_current, 0), '
                     'NULLIF(eq.cycle_time_theoretical, 0))')

        # Objetivo por hora de CADA línea: molde primero, ciclo manual de
        # la operación después. Se calcula por línea y no por turno porque
        # un turno puede haber corrido varias órdenes distintas.
        objetivo_hora = """
            CASE
                WHEN eq.id IS NOT NULL AND eq.cavity_count > 0
                     AND {ciclo} IS NOT NULL
                    THEN 3600.0 / ({ciclo} / eq.cavity_count)
                WHEN op.time_cycle_manual > 0
                    THEN 60.0 / op.time_cycle_manual
                ELSE 0
            END
        """.format(ciclo=ciclo)

        # Solo cuentan como teóricas las unidades esperadas en tiempo
        # PRODUCTIVO y en turno PLANEADO:
        #  - exigirle producción a una máquina detenida por una parada
        #    registrada sería castigar dos veces la disponibilidad;
        #  - en una franja de capacidad apagada (day_period 'lunch') el
        #    objetivo es 0 por diseño, así que la producción real se
        #    reporta pero sin porcentaje contra objetivo (turno extra).
        teoricas = """
            SUM(
                CASE WHEN l.loss_type = 'productive' AND {planned_line}
                    THEN ({objetivo}) * (COALESCE(p.duration, 0) / 60.0)
                    ELSE 0
                END
            )
        """.format(objetivo=objetivo_hora, planned_line=planned_line)

        return """
            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY p.workcenter_id, p.shift_date, p.shift_name
                )                                       AS id,
                p.shift_date                            AS shift_date,
                p.shift_name                            AS shift_name,
                {planned}                               AS shift_is_planned,
                p.workcenter_id                         AS workcenter_id,
                MAX(wc.company_id)                      AS company_id,

                SUM(COALESCE(p.duration, 0))            AS minutos_total,
                SUM(CASE WHEN l.loss_type = 'productive'
                         THEN COALESCE(p.duration, 0) ELSE 0 END)
                                                        AS minutos_productivos,
                SUM(COALESCE(p.x_studio_cantidad, 0))   AS unidades_buenas,
                SUM(COALESCE(p.x_studio_averias, 0))    AS unidades_averias,
                {teoricas}                              AS unidades_teoricas,

                CASE WHEN SUM(COALESCE(p.duration, 0)) > 0
                     THEN 100.0 * SUM(CASE WHEN l.loss_type = 'productive'
                                           THEN COALESCE(p.duration, 0)
                                           ELSE 0 END)
                          / SUM(COALESCE(p.duration, 0))
                END                                     AS disponibilidad,

                CASE WHEN {teoricas} > 0
                     THEN 100.0 * (SUM(COALESCE(p.x_studio_cantidad, 0))
                                   + SUM(COALESCE(p.x_studio_averias, 0)))
                          / {teoricas}
                END                                     AS rendimiento,

                CASE WHEN (SUM(COALESCE(p.x_studio_cantidad, 0))
                           + SUM(COALESCE(p.x_studio_averias, 0))) > 0
                     THEN 100.0 * SUM(COALESCE(p.x_studio_cantidad, 0))
                          / (SUM(COALESCE(p.x_studio_cantidad, 0))
                             + SUM(COALESCE(p.x_studio_averias, 0)))
                END                                     AS calidad,

                CASE WHEN SUM(COALESCE(p.duration, 0)) > 0
                          AND {teoricas} > 0
                          AND (SUM(COALESCE(p.x_studio_cantidad, 0))
                               + SUM(COALESCE(p.x_studio_averias, 0))) > 0
                     THEN (
                        100.0
                        * (SUM(CASE WHEN l.loss_type = 'productive'
                                    THEN COALESCE(p.duration, 0) ELSE 0 END)
                           / SUM(COALESCE(p.duration, 0)))
                        * ((SUM(COALESCE(p.x_studio_cantidad, 0))
                            + SUM(COALESCE(p.x_studio_averias, 0)))
                           / {teoricas})
                        * (SUM(COALESCE(p.x_studio_cantidad, 0))
                           / (SUM(COALESCE(p.x_studio_cantidad, 0))
                              + SUM(COALESCE(p.x_studio_averias, 0))::numeric))
                     )
                END                                     AS oee

            FROM {P} p
            LEFT JOIN mrp_workcenter_productivity_loss l ON l.id = p.loss_id
            LEFT JOIN mrp_workcenter wc                  ON wc.id = p.workcenter_id
            LEFT JOIN mrp_workorder wo                   ON wo.id = p.workorder_id
            LEFT JOIN mrp_routing_workcenter op          ON op.id = wo.operation_id
            LEFT JOIN maintenance_equipment eq
                   ON eq.id = COALESCE(wo.mold_id, op.mold_id)
            WHERE p.workcenter_id IS NOT NULL
            GROUP BY p.workcenter_id, p.shift_date, p.shift_name
        """.format(P=P, planned=planned_expr, teoricas=teoricas)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            "CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._build_query()))
        _logger.info('Vista %s regenerada.', self._table)

    def action_rebuild_view(self):
        """Regenera la vista sin actualizar el módulo."""
        self.sudo().init()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Informe de OEE',
                'message': 'La vista se regeneró correctamente.',
                'type': 'success',
                'sticky': False,
            },
        }
