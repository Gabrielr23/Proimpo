# NOTA MIGRACIÓN 19.0 (requiere verificación manual):
# En Odoo 19 Community (rama 19.0, revisada el 08-10-2026) el método
# resource.calendar._get_flexible_leaves_date YA NO EXISTE. Para recursos
# flexibles, _unavailable_intervals_batch convierte directamente los
# intervalos a UTC sin leer holiday_id, por lo que este override no se
# invoca nunca (queda inerte). Ver README.md, sección "Estado en Odoo 19".
from datetime import datetime, time

import pytz

from odoo import models


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    def _get_flexible_leaves_date(self, res_leaves, resource, tz):
        """Parche temporal para la regresión de Odoo 8227bbbe1410 (PR #261597).

        Reemplaza la implementación de hr_holidays, que tiene dos errores:

        1. Lee ``holiday_id`` con los permisos del usuario actual y lanza
           AccessError a usuarios sin permisos de Ausencias (Gantt de
           Asistencias y Planificación).
        2. Asume que cada intervalo tiene una sola ausencia. Cuando dos
           ausencias (o una ausencia y un festivo) se solapan o son contiguas,
           Odoo las fusiona en un mismo intervalo y ``i[2].holiday_id`` lanza
           "Expected singleton".

        Misma lógica que la original: si el intervalo es de días completos se
        extiende de 00:00 a 23:59:59 en la zona horaria del calendario; si
        alguna ausencia del intervalo es de medio día o por horas, se conservan
        los límites originales. Las ausencias se leen con sudo() solo para
        calcular fechas; no se expone información al usuario.

        No se llama a super(): la versión de hr_holidays es la que falla y la
        de resource solo devuelve [].

        Retirar este módulo cuando Odoo publique la corrección oficial.
        """
        result = []
        for start, stop, meta in res_leaves:
            holidays = meta.sudo().mapped('holiday_id') if meta else self.env['hr.leave']
            partial = any(h.request_unit_half or h.request_unit_hours for h in holidays)
            if partial:
                result.append((start, stop))
            else:
                result.append((
                    tz.localize(datetime.combine(start.date(), time.min)).astimezone(pytz.utc),
                    tz.localize(datetime.combine(stop.date(), time.max)).astimezone(pytz.utc),
                ))
        return result