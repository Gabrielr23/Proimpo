# -*- coding: utf-8 -*-
from odoo import models


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def _recompute_acumulado(self):
        """Recalcula x_studio_acumulado sumando x_studio_cantidad de
        todas las lineas de Seguimiento de tiempo de esta orden.

        Migrado de la Accion automatizada de Studio del instructivo
        original ("Paso 3.2: acumulado de la orden de trabajo").
        Antes el campo se llamaba x_studio_acumulado_1; Laura lo
        renombro a x_studio_acumulado -- este modulo usa el nombre
        actual.
        """
        for wo in self:
            lineas = self.env['mrp.workcenter.productivity'].search([
                ('workorder_id', '=', wo.id),
            ])
            total = sum(lineas.mapped('x_studio_cantidad'))
            wo.write({'x_studio_acumulado': total})
