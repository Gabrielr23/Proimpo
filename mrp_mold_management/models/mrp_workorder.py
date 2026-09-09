# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    mold_id = fields.Many2one(
        'maintenance.equipment', string='Molde',
        domain="[('is_mold', '=', True), "
               "('compatible_workcenter_ids', '=', workcenter_id)]",
        help='Molde instalado para esta orden de trabajo. Solo se listan '
             'moldes marcados como compatibles con el centro de trabajo '
             'seleccionado arriba.',
    )
    mold_hourly_target = fields.Float(
        string='Objetivo por Hora (Molde)', related='mold_id.hourly_target',
        readonly=True, digits=(10, 2),
        help='Objetivo teórico de piezas por hora, según el ciclo y las '
             'cavidades vigentes del molde seleccionado.',
    )

    @api.onchange('workcenter_id')
    def _onchange_workcenter_id_clear_incompatible_mold(self):
        """Si cambia el centro de trabajo y el molde ya no es compatible,
        se limpia en lugar de dejar una combinación inválida sin avisar."""
        for wo in self:
            if wo.mold_id and wo.workcenter_id \
                    and wo.workcenter_id not in wo.mold_id.compatible_workcenter_ids:
                wo.mold_id = False
