# -*- coding: utf-8 -*-
import hashlib
import logging
import time
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

from .oee_sql import OUT_COLS, build_line_sql, drop_relation

_logger = logging.getLogger(__name__)

# Súbase cuando cambie la lógica del cálculo aunque el SQL generado no cambie.
CALC_VERSION = '1.3'
P_HASH = 'mrp_oee_report.calc_hash'
P_CURSOR = 'mrp_oee_report.rebuild_until'      # el histórico ya está al día desde esta fecha
P_DAYS = 'mrp_oee_report.recalc_days'          # margen de recálculo automático (días)
P_REFRESH = 'mrp_oee_report.last_refresh'
REBUILD_BUDGET_S = 50                          # segundos por ejecución de la acción programada
LOCK_KEY = 815002024                           # pg_advisory_xact_lock: un recálculo a la vez

TIME_CLASS = [
    ('running', 'Operando'),
    ('authorized', 'Parada autorizada'),
    ('unplanned', 'Parada no programada'),
]
LOSS_TYPE = [
    ('availability', 'Disponibilidad'),
    ('performance', 'Rendimiento'),
    ('quality', 'Calidad'),
    ('productive', 'Productivo'),
]
STD_SOURCE = [
    ('mold', 'Molde'),
    ('operation', 'Ciclo de la operación'),
    ('none', 'Sin estándar'),
]


class WorkcenterProductivityLoss(models.Model):
    _inherit = 'mrp.workcenter.productivity.loss'

    oee_authorized_stop = fields.Boolean(
        string='Parada autorizada',
        help='Marcar en paradas planeadas o propias del proceso (setup, '
             'cambio de molde o color, purga, limpieza). Su tiempo no resta '
             'Disponibilidad en el OEE: se descuenta antes, como en el '
             'tablero de Access, y se reporta aparte como horas de setup.')


class MrpOeeLine(models.Model):
    """Una fila por tramo de línea de seguimiento de tiempo dentro de un turno,
    con los minutos ya clasificados.

    Es una TABLA que se actualiza por partes (v1.3), no una vista:
      * cada 15 min se recalculan solo los últimos N días (parámetro
        mrp_oee_report.recalc_days, por defecto 3);
      * actualizar el módulo no recalcula nada salvo que cambie el cálculo;
        en ese caso el histórico se rehace en segundo plano, mes a mes;
      * el botón "Recalcular periodo" del tablero rehace las fechas filtradas.
    Nunca bloquea a otros usuarios: los recálculos son DELETE + INSERT por
    rango dentro de una transacción (las lecturas ven los datos anteriores
    hasta el commit)."""
    _name = 'mrp.oee.line'
    _description = 'OEE - Tramo de línea de tiempo por turno'
    _log_access = False
    _order = 'date_start desc'

    workcenter_id = fields.Many2one('mrp.workcenter', 'Centro de Trabajo', readonly=True, index=True)
    company_id = fields.Many2one('res.company', 'Compañía', readonly=True)
    shift_date = fields.Date('Fecha Operativa', readonly=True, index=True)
    shift_name = fields.Char('Turno', readonly=True)
    shift_label = fields.Char('Turno (sin día)', readonly=True)
    shift_is_planned = fields.Boolean('Turno Planeado', readonly=True)
    date_start = fields.Datetime('Inicio', readonly=True)
    workorder_id = fields.Many2one('mrp.workorder', 'Orden de Trabajo', readonly=True)
    production_id = fields.Many2one('mrp.production', 'Orden de Producción', readonly=True)
    product_id = fields.Many2one('product.product', 'Producto', readonly=True)
    operario = fields.Char('Operario', readonly=True)
    loss_id = fields.Many2one('mrp.workcenter.productivity.loss', 'Motivo', readonly=True)
    loss_type = fields.Selection(LOSS_TYPE, 'Categoría', readonly=True)
    authorized_stop = fields.Boolean('Parada autorizada', readonly=True)
    time_class = fields.Selection(TIME_CLASS, 'Clase de tiempo', readonly=True)
    std_source = fields.Selection(STD_SOURCE, 'Origen del estándar', readonly=True)
    std_min_unit = fields.Float('Min. estándar por unidad', readonly=True,
                                digits=(16, 5), aggregator=None)

    productivity_id = fields.Many2one('mrp.workcenter.productivity', 'Línea de tiempo',
                                      readonly=True, index=True, ondelete='cascade')
    es_primera = fields.Boolean('Primer tramo de la línea', readonly=True,
                                help='Para contar cada línea una sola vez cuando se '
                                     'reparte entre varios turnos.')
    paralelo = fields.Boolean('CT con OT en paralelo', readonly=True,
                              help='Centro con etiqueta del parámetro '
                                   'mrp_oee_report.parallel_tags: no se deduplica.')
    olvidada = fields.Boolean(
        'Línea olvidada', readonly=True,
        help='Línea de más de 12 h: no cuenta en el OEE (ni tiempo ni unidades) '
             'hasta que se corrija el registro.')
    min_bruto = fields.Float('Min. según la línea', readonly=True, digits=(16, 2),
                             help='Duración tal como quedó en el seguimiento de '
                                  'tiempo (solo en el primer tramo).')
    min_traslape = fields.Float(
        'Min. traslapados', readonly=True, digits=(16, 2),
        help='Tiempo que otra línea de la misma máquina ya cubría. El reloj '
             'de la máquina se cuenta una sola vez.')
    min_registrado = fields.Float('Min. efectivos', readonly=True, digits=(16, 2),
                                  help='Minutos que cuentan en el OEE: repartidos por '
                                       'turno y sin traslapes.')
    unidades_linea = fields.Float('Unidades de la línea', readonly=True, digits=(16, 0),
                                  help='Buenas tal como se registraron (solo en el '
                                       'primer tramo), incluidas las líneas olvidadas.')
    min_operando = fields.Float('Min. operando', readonly=True, digits=(16, 2))
    min_operando_std = fields.Float('Min. operando con estándar', readonly=True, digits=(16, 2))
    min_autorizada = fields.Float('Min. paradas autorizadas', readonly=True, digits=(16, 2))
    min_no_programada = fields.Float('Min. paradas no programadas', readonly=True, digits=(16, 2))
    unidades_buenas = fields.Float('Unidades buenas', readonly=True, digits=(16, 0))
    unidades_averias = fields.Float('Averías', readonly=True, digits=(16, 0))
    min_estandar = fields.Float('Min. estándar producidos', readonly=True, digits=(16, 2))
    min_valioso = fields.Float('Min. valiosos', readonly=True, digits=(16, 2))
    eventos_parada = fields.Integer('Eventos de parada', readonly=True)
    microparadas = fields.Integer('Microparadas (<5 min)', readonly=True)
    costs_hour = fields.Float('Costo hora CT', readonly=True, aggregator=None)
    oee_target = fields.Float('Meta OEE CT', readonly=True, aggregator=None)

    # ------------------------------------------------------------------
    # Estructura
    # ------------------------------------------------------------------
    def _auto_init(self):
        cr = self.env.cr
        # La vista por turno depende de esta tabla: se recrea en su init().
        drop_relation(cr, 'mrp_oee_report')
        # Versiones 1.1 (vista) y 1.2 (vista materializada) usaban este nombre.
        drop_relation(cr, self._table)
        return super()._auto_init()

    def _calc_hash(self):
        sql = build_line_sql(self.env.cr)
        return hashlib.md5((CALC_VERSION + sql).encode()).hexdigest()

    def init(self):
        """Corre en cada actualización del módulo. Solo marca el histórico
        para recalcular si el cálculo cambió; el trabajo pesado lo hace la
        acción programada, fuera de la actualización."""
        ICP = self.env['ir.config_parameter'].sudo()
        new_hash = self._calc_hash()
        self.env.cr.execute('SELECT 1 FROM %s LIMIT 1' % self._table)
        empty = not self.env.cr.fetchone()
        if empty or ICP.get_param(P_HASH) != new_hash:
            ICP.set_param(P_HASH, new_hash)
            # Pendiente: rehacer desde mañana hacia atrás.
            ICP.set_param(P_CURSOR, fields.Date.to_string(
                fields.Date.context_today(self) + timedelta(days=1)))
            _logger.info('OEE: el cálculo cambió; el histórico se rehará en segundo plano.')

    @api.model
    def _after_update(self):
        """Llamado por data/menu_placement.xml en cada actualización, ya con
        las acciones programadas creadas: recalcula los últimos días (rápido)
        y dispara el rehacer del histórico si quedó pendiente."""
        self.recompute_recent()
        if self._rebuild_pending():
            cron = self.env.ref('mrp_oee_report.cron_rebuild_oee', raise_if_not_found=False)
            if cron:
                cron._trigger()

    # ------------------------------------------------------------------
    # Recálculo por rango
    # ------------------------------------------------------------------
    @api.model
    def _recompute(self, date_from, date_to):
        """Rehace los tramos con fecha operativa entre date_from y date_to."""
        cr = self.env.cr
        self.env.flush_all()
        cr.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_KEY,))
        cr.execute('SET LOCAL jit = off')
        params = {'df': date_from, 'dt': date_to}
        cr.execute('DELETE FROM %s WHERE shift_date BETWEEN %%(df)s AND %%(dt)s'
                   % self._table, params)
        cols = ', '.join(OUT_COLS)
        updates = ', '.join('%s = EXCLUDED.%s' % (c, c) for c in OUT_COLS if c != 'id')
        cr.execute('INSERT INTO %s (%s) SELECT %s FROM (%s) q '
                   'ON CONFLICT (id) DO UPDATE SET %s'
                   % (self._table, cols, cols, build_line_sql(cr), updates), params)
        self.env.invalidate_all()
        return True

    def _recalc_days(self):
        try:
            return max(int(self.env['ir.config_parameter'].sudo().get_param(P_DAYS, 3)), 1)
        except ValueError:
            return 3

    @api.model
    def recompute_recent(self):
        today = fields.Date.context_today(self)
        self._recompute(today - timedelta(days=self._recalc_days()), today + timedelta(days=1))
        self.env['ir.config_parameter'].sudo().set_param(
            P_REFRESH, fields.Datetime.to_string(fields.Datetime.now()))
        return True

    @api.model
    def recompute_period(self, date_from, date_to):
        """Rehace un periodo completo, mes a mes (botón del tablero)."""
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        start = date_from
        while start <= date_to:
            end = min(start + relativedelta(months=1) - timedelta(days=1), date_to)
            self._recompute(start, end)
            start = end + timedelta(days=1)
        return True

    # ------------------------------------------------------------------
    # Histórico en segundo plano
    # ------------------------------------------------------------------
    def _oldest_date(self):
        self.env.cr.execute('SELECT MIN(date_start)::date FROM mrp_workcenter_productivity')
        return self.env.cr.fetchone()[0]

    @api.model
    def _rebuild_pending(self):
        cursor = self.env['ir.config_parameter'].sudo().get_param(P_CURSOR)
        oldest = self._oldest_date()
        return bool(cursor and oldest and fields.Date.to_date(cursor) > oldest)

    @api.model
    def rebuild_status(self):
        ICP = self.env['ir.config_parameter'].sudo()
        if not self._rebuild_pending():
            return {'pending': False}
        return {'pending': True, 'until': ICP.get_param(P_CURSOR),
                'oldest': fields.Date.to_string(self._oldest_date())}

    @api.model
    def _cron_rebuild(self):
        """Rehace el histórico de lo más reciente hacia atrás, un mes por
        paso, con commit entre pasos y un tope de tiempo por ejecución."""
        ICP = self.env['ir.config_parameter'].sudo()
        oldest = self._oldest_date()
        started = time.monotonic()
        while True:
            cursor = ICP.get_param(P_CURSOR)
            if not cursor or not oldest:
                return
            end = fields.Date.to_date(cursor) - timedelta(days=1)
            if end < oldest:
                ICP.set_param(P_CURSOR, False)
                _logger.info('OEE: histórico recalculado completo.')
                return
            start = max(end - relativedelta(months=1) + timedelta(days=1), oldest)
            self._recompute(start, end)
            ICP.set_param(P_CURSOR, fields.Date.to_string(start))
            self.env.cr.commit()
            if time.monotonic() - started > REBUILD_BUDGET_S:
                self.env.ref('mrp_oee_report.cron_rebuild_oee')._trigger()
                return

    @api.model
    def refresh_data(self):
        """Botón Actualizar y acción programada cada 15 min: solo los
        últimos días."""
        return self.recompute_recent()

    @api.model
    def _cron_refresh(self):
        self.recompute_recent()
