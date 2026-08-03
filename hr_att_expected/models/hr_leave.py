# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import models


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    def _pa_recalcular_asistencias(self):
        """Recalcula estado/tiempos esperados de las asistencias del empleado
        dentro del rango de la ausencia, para que queden 'Valida con ausencia'
        (o se reviertan si el permiso se rechaza) sin recalcular a mano."""
        Att = self.env['hr.attendance'].sudo()
        for leave in self:
            if not leave.employee_id or not leave.date_from or not leave.date_to:
                continue
            att = Att.search([
                ('employee_id', '=', leave.employee_id.id),
                ('check_in', '<=', leave.date_to),
                ('check_out', '>=', leave.date_from - timedelta(days=1)),
            ])
            if att:
                att._compute_expected_times()

    def write(self, vals):
        res = super().write(vals)
        # Si cambia el estado de aprobacion o el rango de fechas, reevaluar las
        # asistencias afectadas (aplica o revierte 'Valida con ausencia').
        if any(k in vals for k in ('state', 'date_from', 'date_to')):
            self._pa_recalcular_asistencias()
        return res
