from odoo import models
from odoo.addons.resource.models.utils import make_aware


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def _mwmd_unavailable_domain(self, workcenter, date_from):
        """Tiempo no disponible al calcular fechas manuales: ausencias y
        mantenimientos del centro de trabajo, SIN las reservas de órdenes de trabajo."""
        domain = [('time_type', 'in', ['leave', 'other'])]
        wo_leaves = self.env['mrp.workorder'].sudo().search([
            ('workcenter_id', '=', workcenter.id),
            ('leave_id', '!=', False),
            ('leave_id.date_to', '>=', date_from),
        ]).leave_id
        if self.leave_id:
            wo_leaves |= self.leave_id._origin
        if wo_leaves:
            domain.append(('id', 'not in', wo_leaves.ids))
        return domain

    def _calculate_date_finished(self, date_start=False):
        workcenter = self.env.context.get('new_workcenter_id') or self.workcenter_id
        date_start = date_start or self.date_start
        if not workcenter.resource_calendar_id or not date_start:
            return super()._calculate_date_finished(date_start=date_start)
        return workcenter.resource_calendar_id.plan_hours(
            self.duration_expected / 60.0, date_start,
            compute_leaves=True,
            domain=self._mwmd_unavailable_domain(workcenter, date_start),
            resource=workcenter.resource_id,
        )

    def _calculate_duration_expected(self, date_start=False, date_finished=False):
        workcenter = self.workcenter_id
        date_start = date_start or self.date_start
        date_finished = date_finished or self.date_finished
        if not workcenter.resource_calendar_id or not date_start or not date_finished:
            return super()._calculate_duration_expected(date_start=date_start, date_finished=date_finished)
        start, _revert = make_aware(date_start)
        stop, _revert = make_aware(date_finished)
        resource = workcenter.resource_id
        intervals = workcenter.resource_calendar_id._work_intervals_batch(
            start, stop, resources=resource,
            domain=self._mwmd_unavailable_domain(workcenter, date_start),
        )[resource.id]
        return sum((i_stop - i_start).total_seconds() for i_start, i_stop, _meta in intervals) / 60.0
