# -*- coding: utf-8 -*-
from odoo import models, fields, api

PILA_NOVEDAD = [
    ('worked', 'Dias trabajados (cotiza normal)'),
    ('VAC', 'Vacaciones (VAC)'),
    ('LR', 'Licencia remunerada (LR)'),
    ('IGE', 'Incapacidad general (IGE)'),
    ('IRL', 'Incapacidad laboral (IRL)'),
    ('LMA', 'Licencia maternidad/paternidad (LMA)'),
    ('SLN', 'Suspension / no remunerada (SLN)'),
]


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    pila_novedad = fields.Selection(
        PILA_NOVEDAD, string="Novedad PILA", default='worked',
        help="Como se reporta esta ausencia en la PILA. Determina si genera linea propia, "
             "si cotiza y a que subsistemas.")

    @api.model
    def pila_novedad_asignar_defecto(self):
        """Asigna la novedad PILA por defecto segun el nombre del tipo de ausencia."""
        def clasificar(nombre):
            n = (nombre or '').upper()
            if 'VACACION' in n:
                return 'VAC'
            if 'INCAPACIDAD' in n and ('LABORAL' in n or 'RIESGO' in n or 'ATEP' in n):
                return 'IRL'
            if 'INCAPACIDAD' in n:
                return 'IGE'
            if 'MATERNIDAD' in n or 'PATERNIDAD' in n:
                return 'LMA'
            if any(k in n for k in ('NO PAGAD', 'NO REMUNERAD', 'SUSPENSI', 'INJUSTIFICAD')):
                return 'SLN'
            if any(k in n for k in ('LUTO', 'REMUNERADA', 'CALAMIDAD', 'FAMILIA', 'PERMISO',
                                    'LICENCIA', 'CITA', 'EXAMEN', 'VOTACI', 'DILIGENCIA',
                                    'CAPACITAC', 'BIENESTAR', 'ODONTOLOG', 'URGENCIA',
                                    'ACOMPAÑAR', 'REUNIONES', 'SEGUIMIENTO', 'ESPECIAL', 'CARGOS')):
                return 'LR'
            return 'worked'
        for lt in self.search([]):
            c = clasificar(lt.name)
            if c:
                lt.pila_novedad = c
        return True
