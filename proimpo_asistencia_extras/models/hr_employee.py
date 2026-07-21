# -*- coding: utf-8 -*-
from odoo import models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _pa_gerencia(self):
        """Departamento de nivel 'Gerencia': se sube por el arbol hasta el
        departamento que cuelga directamente de la raiz (Gerencia General)."""
        self.ensure_one()
        d = self.department_id
        while d and d.parent_id and d.parent_id.parent_id:
            d = d.parent_id
        return d

    def _pa_gerente_aprobador(self):
        """Gerente del area, que es quien aprueba las horas extra."""
        self.ensure_one()
        g = self._pa_gerencia()
        return g.manager_id if g and g.manager_id else self.env['hr.employee']

    def _pa_email(self):
        self.ensure_one()
        return self.work_email or (self.user_id and self.user_id.email) or ''
