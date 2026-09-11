# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'

    mold_id = fields.Many2one(
        'maintenance.equipment', string='Molde',
        domain="[('is_mold', '=', True), "
               "'|', ('compatible_workcenter_ids', '=', False), "
               "('compatible_workcenter_ids', '=', workcenter_id)]",
        context={"default_is_mold": True},
        help='Molde que ejecuta esta operación. Vínculo uno a uno: esta '
             'operación tiene un único molde, y su ciclo se corrige aquí '
             'automáticamente cuando se aplica una revisión del molde en '
             'Mantenimiento → Moldes. Si el molde no existe todavía, use '
             '"Crear y editar..." en este mismo campo: el nuevo registro '
             'nace marcado como molde, así que la pestaña de cavidades y '
             'ciclo aparece de inmediato, sin pasos ocultos.',
    )
