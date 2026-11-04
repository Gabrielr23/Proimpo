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
        """Traslada los valores verificados al molde y, si corresponde,
        empuja el nuevo ciclo a la operación de ruta vinculada.

        Aplicar el molde es deliberadamente manual (un responsable confirma
        que el cambio es real). Empujar a la ruta ocurre automáticamente en
        ese mismo momento: es el punto donde ya tiene sentido corregir la
        fuente, para que las órdenes nuevas nazcan bien sin un paso aparte.
        """
        pending_count = 0
        push_summary = {'updated': [], 'skipped_auto': [], 'unlinked': []}

        for log in self:
            vals = {}
            if log.cavity_count_verified:
                vals['cavity_count'] = log.cavity_count_verified
            if log.cycle_time_verified:
                vals['cycle_time_current'] = log.cycle_time_verified
            if not vals:
                continue

            log.equipment_id.sudo().write(vals)
            log.applied = True

            pending_count += self.env['mrp.workorder'].sudo().search_count([
                ('mold_id', '=', log.equipment_id.id),
                ('state', 'in', ('pending', 'waiting', 'ready')),
            ])

            result = log.equipment_id._push_cycle_to_routing()
            for k in push_summary:
                push_summary[k].extend(result[k])

        lines = ['Los valores verificados se aplicaron al molde.']

        if push_summary['updated']:
            lines.append('Operación(es) de LdM actualizada(s): %s.'
                        % ', '.join(push_summary['updated']))
        if push_summary['skipped_auto']:
            lines.append(
                'ATENCIÓN: %s está(n) en modo de tiempo automático — Odoo '
                'recalcula ese ciclo solo desde el histórico, así que este '
                'valor NO tuvo efecto. Cámbielas a modo manual si quiere que '
                'el molde controle el ciclo.' % ', '.join(push_summary['skipped_auto'])
            )
        if push_summary['unlinked']:
            lines.append(
                'El molde %s no tiene ninguna operación de LdM vinculada '
                '(campo "Operación de LdM"): las órdenes nuevas seguirán '
                'naciendo con el ciclo anterior hasta que la vincule.'
                % ', '.join(push_summary['unlinked'])
            )
        if pending_count:
            lines.append(
                'Hay %s orden(es) de trabajo ya creadas y aún no iniciadas '
                'que usan este molde: no se recalculan solas, ábralas y use '
                '"Aplicar duración del molde" si corresponde.' % pending_count
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Bitácora de molde',
                'message': ' '.join(lines),
                'type': 'warning' if (push_summary['skipped_auto']
                                      or push_summary['unlinked']) else 'success',
                'sticky': bool(pending_count or push_summary['skipped_auto']
                              or push_summary['unlinked']),
            },
        }
