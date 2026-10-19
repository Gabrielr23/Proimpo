# -*- coding: utf-8 -*-
from odoo import fields, models, tools

from .oee_sql import build_line_sql

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
    """Una fila por línea de seguimiento de tiempo, con los minutos ya
    clasificados. Base del tablero y de cualquier agrupación: los % se
    calculan SIEMPRE sobre sumas de minutos, nunca promediando %."""
    _name = 'mrp.oee.line'
    _description = 'OEE - Línea de tiempo'
    _auto = False
    _order = 'date_start desc'

    workcenter_id = fields.Many2one('mrp.workcenter', 'Centro de Trabajo', readonly=True)
    company_id = fields.Many2one('res.company', 'Compañía', readonly=True)
    shift_date = fields.Date('Fecha Operativa', readonly=True)
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

    min_registrado = fields.Float('Min. registrados', readonly=True, digits=(16, 2))
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

    def init(self):
        # La vista por turno depende de esta: se elimina primero.
        tools.drop_view_if_exists(self.env.cr, 'mrp_oee_report')
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('CREATE OR REPLACE VIEW %s AS (%s)'
                            % (self._table, build_line_sql(self.env.cr)))
