# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpMoldRevisionLog(models.Model):
    _name = 'mrp.mold.revision.log'
    _description = 'Bitácora de Revisión de Molde'
    _order = 'revision_date desc, id desc'
    _rec_name = 'equipment_id'

    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Molde', required=True,
        domain=[('is_mold', '=', True)], ondelete='cascade')

    revision_date = fields.Date(string='Fecha de Revisión', required=True,
                                default=fields.Date.context_today)
    cavity_count_verified = fields.Integer(string='Cavidades Verificadas')
    cycle_time_verified = fields.Float(string='Ciclo Verificado (seg)', digits=(10, 2))

    analysis = fields.Text(string='Análisis')
    action_to_take = fields.Char(string='Acción a Realizar')
    responsible_id = fields.Many2one('res.users', string='Responsable')
    execution_date = fields.Date(string='Fecha de Ejecución de la Acción')
    complies = fields.Boolean(
        string='¿Cumple con la Fecha de Ejecución?',
        help='Indica si la acción se ejecutó dentro del plazo previsto.')
    notes = fields.Text(string='Observaciones')

    applied = fields.Boolean(
        string='Aplicado al Molde', readonly=True,
        help='Se marca automáticamente cuando esta revisión actualiza las '
             'cavidades/ciclo vigentes del molde.')

    def action_apply_to_mold(self):
        """Traslada los valores verificados al molde.

        Deliberadamente manual: el ajuste de un dato que afecta el objetivo
        de producción de toda una línea no debe ocurrir solo porque alguien
        guardó una fila de bitácora, sino porque un responsable confirmó
        que el cambio es real.
        """
        for log in self:
            vals = {}
            if log.cavity_count_verified:
                vals['cavity_count'] = log.cavity_count_verified
            if log.cycle_time_verified:
                vals['cycle_time_current'] = log.cycle_time_verified
            if vals:
                log.equipment_id.sudo().write(vals)
                log.applied = True
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Bitácora de molde',
                'message': 'Los valores verificados se aplicaron al molde.',
                'type': 'success',
                'sticky': False,
            },
        }
