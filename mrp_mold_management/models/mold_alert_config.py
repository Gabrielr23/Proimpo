# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from .mold_alerts import PARAMS, USER_PARAMS


class MrpMoldAlertConfig(models.TransientModel):
    _name = 'mrp.mold.alert.config'
    _description = 'Configuración de alertas de moldes fuera de su ubicación'

    days_repair = fields.Integer(
        string='1.er aviso: días en reparación',
        help='Cuando un molde en reparación lleva más días que estos, se '
             'envía una actividad al jefe de mantenimiento.')
    chief_user_id = fields.Many2one(
        'res.users', string='Jefe de mantenimiento',
        help='Recibe el primer aviso de reparación y los avisos de maquila '
             'o de molde fuera sin solicitud. Si se deja vacío, le llega al '
             'técnico o propietario del molde.')
    days_escalation = fields.Integer(
        string='Escalamiento: días en reparación',
        help='Cuando el molde sigue en reparación después de estos días, '
             'se envía una segunda actividad al jefe superior.')
    boss_user_id = fields.Many2one(
        'res.users', string='Jefe superior',
        help='Recibe el escalamiento. Si se deja vacío, no hay segundo '
             'aviso.')
    days_external = fields.Integer(
        string='Días en proveedor externo (producción)',
        help='Cuando un molde lleva más días que estos produciendo en un '
             'proveedor externo (centro de trabajo marcado como externo).')
    external_user_id = fields.Many2one(
        'res.users', string='Responsable del aviso',
        help='Recibe el aviso de molde en proveedor externo. Si se deja '
             'vacío, le llega al jefe de mantenimiento.')
    days_maquila = fields.Integer(
        string='Días fuera, otras salidas',
        help='Para moldes que están fuera pero ni en reparación ni en un '
             'proveedor externo produciendo.')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        Alerts = self.env['mrp.mold.alerts']
        res.update({
            'days_repair': Alerts._param('dias_reparacion'),
            'days_escalation': Alerts._param('dias_escalamiento'),
            'days_maquila': Alerts._param('dias_maquila'),
            'days_external': Alerts._param('dias_externo'),
            'external_user_id': Alerts._configured_user('externo').id or False,
            'chief_user_id': Alerts._configured_user('jefe').id or False,
            'boss_user_id': Alerts._configured_user('superior').id or False,
        })
        return res

    def action_save(self):
        self.ensure_one()
        if min(self.days_repair, self.days_escalation, self.days_maquila,
               self.days_external) < 1:
            raise UserError('Los días deben ser al menos 1.')
        if self.days_escalation <= self.days_repair:
            raise UserError(
                'El escalamiento debe ser DESPUÉS del primer aviso: más días '
                'que los del primer aviso (%s).' % self.days_repair)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(PARAMS['dias_reparacion'][0], self.days_repair)
        ICP.set_param(PARAMS['dias_escalamiento'][0], self.days_escalation)
        ICP.set_param(PARAMS['dias_maquila'][0], self.days_maquila)
        ICP.set_param(PARAMS['dias_externo'][0], self.days_external)
        ICP.set_param(USER_PARAMS['externo'], self.external_user_id.id or '')
        ICP.set_param(USER_PARAMS['jefe'], self.chief_user_id.id or '')
        ICP.set_param(USER_PARAMS['superior'], self.boss_user_id.id or '')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Alertas guardadas',
                'message': 'La configuración aplica desde la próxima '
                           'ejecución diaria.',
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
