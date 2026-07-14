# -*- coding: utf-8 -*-
from odoo import models, fields, api

CASILLAS = [
    ('36', '36 - Salarios'),
    ('37', '37 - Bonos/vales de servicio'),
    ('38', '38 - Honorarios'),
    ('39', '39 - Servicios'),
    ('40', '40 - Comisiones'),
    ('41', '41 - Prestaciones sociales'),
    ('42', '42 - Viaticos'),
    ('43', '43 - Gastos de representacion'),
    ('44', '44 - Compensaciones cooperativo'),
    ('45', '45 - Otros pagos'),
    ('46', '46 - Cesantias e intereses pagadas al empleado'),
    ('48', '48 - Pensiones'),
    ('50', '50 - Aportes salud (trabajador)'),
    ('51', '51 - Aportes pension y FSP (trabajador)'),
    ('52', '52 - Cotizaciones voluntarias RAIS'),
    ('53', '53 - Aportes voluntarios a pensiones'),
    ('54', '54 - Aportes AFC/AVC'),
    ('55', '55 - Retencion en la fuente'),
]


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    cert220_casilla = fields.Selection(
        CASILLAS, string="Casilla Certificado 220",
        help="Casilla del formato 220 (Certificado de ingresos y retenciones) a la que "
             "suma esta regla. La casilla 47 (cesantias consignadas) se calcula aparte.")

    @api.model
    def cert220_asignar_defecto(self):
        """Asigna una casilla por defecto segun el codigo/categoria de cada regla (heuristica)."""
        def cas(rule):
            code = (rule.code or '').upper()
            cat = (rule.category_id.code or '').upper()
            if any(k in code for k in ('RTF', 'RETEFUENTE', 'RETENCION')):
                return '55'
            if 'FSP' in code or 'PENS' in code:
                return '51'
            if 'SALUD' in code or 'EPS' in code:
                return '50'
            if 'AFC' in code or 'AVC' in code:
                return '54'
            if 'APV' in code or 'VOLUNT' in code:
                return '53'
            if any(k in code for k in ('CESANT', 'CES', 'INTCES', 'INTERES')):
                return '46'
            if 'COMIS' in code:
                return '40'
            if any(k in code for k in ('PRIMA', 'VAC')):
                return '41'
            if any(k in code for k in ('TRANS', 'AUXROD', 'RODAM', 'BONO', 'AUXIL', 'NOSAL')):
                return '45'
            if cat == 'DEVSAL' or any(k in code for k in ('BASIC', 'SUELDO', 'HE', 'REC', 'DOMIN', 'FESTIVO')):
                return '36'
            return False
        for rule in self.search([]):
            c = cas(rule)
            if c and not rule.cert220_casilla:
                rule.cert220_casilla = c
        return True
