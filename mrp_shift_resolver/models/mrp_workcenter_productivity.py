# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpWorkcenterProductivity(models.Model):
    _inherit = 'mrp.workcenter.productivity'

    shift_name = fields.Char(
        string='Turno', compute='_compute_shift_info', store=True, index=True,
        help='Turno al que pertenece esta línea, según el calendario del '
             'centro de trabajo ("Lunes Turno 3"). Vacío si el centro de '
             'trabajo no tiene calendario o la hora cae en un hueco.')
    shift_date = fields.Date(
        string='Fecha Operativa', compute='_compute_shift_info',
        store=True, index=True,
        help='Día en que ARRANCÓ el turno. Una línea de las 02:00 del '
             'martes que pertenece a "Lunes Turno 3" tiene fecha operativa '
             'del lunes. Es el campo por el que se agrupa el OEE diario, '
             'para que el turno nocturno no se sume al día equivocado.')
    shift_is_planned = fields.Boolean(
        string='Turno Planeado', compute='_compute_shift_info', store=True,
        help='False si la franja es de capacidad apagada (day_period='
             '"lunch"). La producción real registrada aquí NO se descarta: '
             'se reporta como turno extra / no planeado, con objetivo 0.')

    @api.depends('workcenter_id', 'date_start')
    def _compute_shift_info(self):
        """Almacenado a propósito, por dos razones:

        1. La Fase B (vista SQL de OEE) agrupa por turno, y SQL no puede
           leer campos calculados no almacenados.
        2. Integridad histórica: al quedar grabado, un cambio futuro de
           calendario no reescribe el turno de registros ya cerrados.
        """
        Resolver = self.env['mrp.shift.resolver']
        for rec in self:
            if rec.workcenter_id and rec.date_start:
                info = Resolver.resolve_shift(rec.workcenter_id, rec.date_start)
            else:
                info = {'shift_name': False, 'shift_date': False,
                        'is_planned': False}
            rec.shift_name = info['shift_name']
            rec.shift_date = info['shift_date']
            rec.shift_is_planned = info['is_planned']
