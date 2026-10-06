# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    is_mold_request = fields.Boolean(
        string='Es de un Molde', related='equipment_id.is_mold',
        store=True, readonly=True)

    repair_location_type = fields.Selection([
        ('interno', 'Taller interno'),
        ('externo', 'Taller externo'),
    ], string='Dónde se Repara', default='interno',
        help='Determina si el molde sale de la planta. De aquí sale el '
             'conteo de días fuera y la estadística por taller.')
    repair_partner_id = fields.Many2one(
        'res.partner', string='Taller Externo',
        help='A qué taller se envió. Sin este dato se puede contar "días '
             'fuera", pero no "días por taller", que es lo que sirve para '
             'negociar tiempos de respuesta.')

    repair_days = fields.Integer(
        string='Días en Reparación', compute='_compute_repair_days',
        store=True,
        help='Días entre la solicitud y su cierre. Si sigue abierta, '
             'cuenta hasta hoy.')

    @api.depends('request_date', 'close_date', 'stage_id.done')
    def _compute_repair_days(self):
        hoy = fields.Date.context_today(self)
        for req in self:
            if not req.request_date:
                req.repair_days = 0
                continue
            fin = req.close_date or hoy
            req.repair_days = (fin - req.request_date).days

    @api.onchange('repair_location_type')
    def _onchange_repair_location_type(self):
        if self.repair_location_type != 'externo':
            self.repair_partner_id = False
