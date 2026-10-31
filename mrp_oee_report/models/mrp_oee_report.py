# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import fields, models

from .oee_sql import drop_relation

_logger = logging.getLogger(__name__)


class MrpOeeReport(models.Model):
    """OEE por centro de trabajo x fecha operativa x turno.

    Los % de cada fila son correctos para ESA fila. No se suman ni se
    promedian al agrupar (aggregator=None): para consolidados usar el
    Tablero OEE, que calcula sobre sumas de minutos."""
    _name = 'mrp.oee.report'
    _description = 'OEE por Turno'
    _auto = False
    _rec_name = 'shift_name'
    _order = 'shift_date desc, workcenter_id, shift_name'

    shift_date = fields.Date('Fecha Operativa', readonly=True)
    shift_name = fields.Char('Turno', readonly=True)
    shift_is_planned = fields.Boolean('Turno Planeado', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Centro de Trabajo', readonly=True)
    company_id = fields.Many2one('res.company', 'Compañía', readonly=True)

    minutos_registrados = fields.Float('Min. registrados', readonly=True, digits=(16, 2))
    minutos_autorizados = fields.Float('Min. paradas autorizadas', readonly=True, digits=(16, 2))
    minutos_cargados = fields.Float('Min. cargados', readonly=True, digits=(16, 2),
                                    help='Registrados menos paradas autorizadas.')
    minutos_no_programados = fields.Float('Min. paradas no programadas', readonly=True, digits=(16, 2))
    minutos_operando = fields.Float('Min. operando', readonly=True, digits=(16, 2))
    minutos_estandar = fields.Float('Min. estándar producidos', readonly=True, digits=(16, 2))
    minutos_valiosos = fields.Float('Min. valiosos', readonly=True, digits=(16, 2))
    unidades_buenas = fields.Float('Unidades buenas', readonly=True, digits=(16, 0))
    unidades_averias = fields.Float('Averías', readonly=True, digits=(16, 0))
    oee_target = fields.Float('Meta OEE %', readonly=True, aggregator=None)

    disponibilidad = fields.Float('Disponibilidad %', readonly=True, digits=(16, 1),
                                  aggregator=None,
                                  help='Min. operando / min. cargados.')
    rendimiento = fields.Float('Rendimiento %', readonly=True, digits=(16, 1),
                               aggregator=None,
                               help='Min. estándar de lo producido / min. operando '
                                    '(solo líneas con ciclo estándar).')
    calidad = fields.Float('Calidad %', readonly=True, digits=(16, 1),
                           aggregator=None,
                           help='Buenas / (buenas + averías).')
    oee = fields.Float('OEE %', readonly=True, digits=(16, 1), aggregator=None,
                       help='Disponibilidad x Rendimiento x Calidad.')

    def _build_query(self):
        d = "NULLIF(SUM(x.min_operando) + SUM(x.min_no_programada), 0)"
        r = "NULLIF(SUM(x.min_operando_std), 0)"
        c = "NULLIF(SUM(x.unidades_buenas) + SUM(x.unidades_averias), 0)"
        return """
            SELECT
                ROW_NUMBER() OVER (ORDER BY x.workcenter_id, x.shift_date,
                                   x.shift_name)           AS id,
                x.shift_date, x.shift_name,
                BOOL_OR(x.shift_is_planned)                 AS shift_is_planned,
                x.workcenter_id,
                MAX(x.company_id)                           AS company_id,
                SUM(x.min_registrado)                       AS minutos_registrados,
                SUM(x.min_autorizada)                       AS minutos_autorizados,
                SUM(x.min_operando) + SUM(x.min_no_programada) AS minutos_cargados,
                SUM(x.min_no_programada)                    AS minutos_no_programados,
                SUM(x.min_operando)                         AS minutos_operando,
                SUM(x.min_estandar)                         AS minutos_estandar,
                SUM(x.min_valioso)                          AS minutos_valiosos,
                SUM(x.unidades_buenas)                      AS unidades_buenas,
                SUM(x.unidades_averias)                     AS unidades_averias,
                MAX(x.oee_target)                           AS oee_target,
                100.0 * SUM(x.min_operando) / {d}           AS disponibilidad,
                100.0 * SUM(x.min_estandar) / {r}           AS rendimiento,
                100.0 * SUM(x.unidades_buenas) / {c}        AS calidad,
                100.0 * (SUM(x.min_operando) / {d})
                      * (SUM(x.min_estandar) / {r})
                      * (SUM(x.unidades_buenas) / {c})      AS oee
            FROM mrp_oee_line x
            GROUP BY x.workcenter_id, x.shift_date, x.shift_name
        """.format(d=d, r=r, c=c)

    def init(self):
        drop_relation(self.env.cr, self._table)
        self.env.cr.execute('CREATE OR REPLACE VIEW %s AS (%s)'
                            % (self._table, self._build_query()))
        _logger.info('Vista %s regenerada.', self._table)

    def action_rebuild_view(self):
        """Regenera la vista por turno y manda a rehacer todo el histórico de
        OEE en segundo plano (no bloquea a nadie)."""
        self.sudo().init()
        Line = self.env['mrp.oee.line'].sudo()
        self.env['ir.config_parameter'].sudo().set_param(
            'mrp_oee_report.rebuild_until',
            fields.Date.to_string(fields.Date.context_today(self) + timedelta(days=1)))
        Line.recompute_recent()
        cron = self.env.ref('mrp_oee_report.cron_rebuild_oee', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Informe de OEE',
                'message': 'Los últimos días ya están al día. El resto del histórico '
                           'se recalcula en segundo plano.',
                'type': 'success',
                'sticky': False,
            },
        }
