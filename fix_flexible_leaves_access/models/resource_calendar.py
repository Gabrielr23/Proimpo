from odoo import models


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    def _get_flexible_leaves_date(self, res_leaves, resource, tz):
        """Parche temporal para la regresión de Odoo 8227bbbe1410 (PR #261597).

        hr_holidays lee ``holiday_id.request_unit_half`` y
        ``holiday_id.request_unit_hours`` sobre los registros de ausencias con
        los permisos del usuario actual. Si el usuario no tiene acceso a una de
        esas ausencias (hr.leave), se lanza un AccessError y no carga el Gantt
        de Asistencias ni el de Planificación.

        Se pasan los registros de ``resource.calendar.leaves`` con sudo() para
        que la lectura de ``holiday_id`` no dependa de los permisos del
        usuario. El método solo devuelve intervalos de fechas, por lo que no
        se expone ningún dato de la ausencia.

        Retirar este módulo cuando Odoo publique la corrección oficial.
        """
        res_leaves = [
            (start, stop, meta.sudo() if meta else meta)
            for start, stop, meta in res_leaves
        ]
        return super()._get_flexible_leaves_date(res_leaves, resource, tz)
