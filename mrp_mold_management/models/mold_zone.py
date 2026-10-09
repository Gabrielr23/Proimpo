# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpMoldZone(models.Model):
    _name = 'mrp.mold.zone'
    _description = 'Zona de Almacenamiento de Moldes'
    _order = 'sequence, name'

    name = fields.Char(string='Zona', required=True, index=True)
    code = fields.Char(string='Código')
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)

    zone_type = fields.Selection([
        ('rack', 'Rack'),
        ('taller', 'Taller'),
        ('piso', 'Piso / Zona abierta'),
        ('otro', 'Otro'),
    ], string='Tipo', default='rack', required=True,
        help='Solo informativo, para agrupar y filtrar. Un rack tiene '
             'posiciones (0-A, 1-B...); un taller o una zona de piso '
             'normalmente no.')

    has_positions = fields.Boolean(
        string='Usa Posiciones', default=True,
        help='Marque si dentro de esta zona los moldes se ubican por '
             'posición (0-A, 1-B...). En TALLER o PISO normalmente no.')

    note = fields.Text(string='Observaciones')

    mold_ids = fields.One2many(
        'maintenance.equipment', 'home_zone_id', string='Moldes Almacenados Aquí')
    mold_count = fields.Integer(string='# Moldes', compute='_compute_mold_count')

    def _compute_mold_count(self):
        for zone in self:
            zone.mold_count = len(zone.mold_ids)

    def action_view_molds(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Moldes almacenados en %s' % self.name,
            'res_model': 'maintenance.equipment',
            'view_mode': 'list,form',
            'domain': [('home_zone_id', '=', self.id)],
            'context': {'default_home_zone_id': self.id, 'default_is_mold': True},
        }
