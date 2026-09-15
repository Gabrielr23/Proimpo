# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpWorkcenterProductivity(models.Model):
    _inherit = 'mrp.workcenter.productivity'

    shift_name = fields.Char(
        string='Turno', compute='_compute_shift_info',
        help='Turno al que pertenece esta línea, según el calendario del '
             'centro de trabajo. "Lunes Turno 3", por ejemplo. Vacío si el '
             'centro de trabajo no tiene calendario asignado o hay un '
             'hueco en el calendario para esa hora.')
    shift_is_planned = fields.Boolean(
        string='Turno Planeado', compute='_compute_shift_info',
        help='False si la franja es de capacidad apagada (day_period='
             '"lunch": fin de semana, turno reducido). La producción real '
             'registrada aquí NO se descarta — solo su objetivo es 0.')

    @api.depends('workcenter_id', 'date_start')
    def _compute_shift_info(self):
        Resolver = self.env['mrp.shift.resolver']
        for rec in self:
            if rec.workcenter_id and rec.date_start:
                info = Resolver.resolve_shift(rec.workcenter_id, rec.date_start)
            else:
                info = {'shift_name': False, 'is_planned': False}
            rec.shift_name = info['shift_name']
            rec.shift_is_planned = info['is_planned']
