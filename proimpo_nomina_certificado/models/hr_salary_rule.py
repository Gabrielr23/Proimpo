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

    @staticmethod
    def _cert220_casilla_para(rule):
        """Casilla del 220 segun el codigo/categoria/tipo de la regla. Solo entran al
        certificado los INGRESOS del trabajador (devengados) y sus DEDUCCIONES de
        seguridad social / voluntarios / retencion. Se EXCLUYEN los aportes patronales,
        las provisiones, los prestamos y las reglas de calculo."""
        code = (rule.code or '').upper()
        cat = (rule.category_id.code or '').upper()
        tc = rule.type_concept

        # Excluir: aportes patronales, provisiones, reglas de calculo (no van al 220)
        if cat in ('APORTE', 'PROV', 'BASE', 'GROSS', 'NET'):
            return False

        # Deducciones del trabajador
        if tc == 'deduction':
            if code == 'RTF' or 'RETEN' in code:
                return '55'
            if code == 'AFC' or 'AVC' in code:
                return '54'
            if code == 'PENSVOL' or 'VOLUNT' in code:
                return '53'
            if code in ('FSP', 'PENS') or code.startswith('PENS'):
                return '51'
            if code == 'SALUD' or 'EPS' in code:
                return '50'
            return False  # LIBR, PREST y otras deducciones no van al 220

        # Ingresos del trabajador (devengados)
        if tc == 'earn':
            if code in ('CESPG', 'INTCES') or 'CESANT' in code:
                return '46'
            if code in ('COM', 'MVCOM', 'MNCOM') or 'COMIS' in code:
                return '40'
            if code in ('PRIMA', 'VAC', 'VACCOMP'):
                return '41'
            if cat == 'DEVNOSAL':
                return '45'          # bonif. no salarial, mayores/menores no salariales
            if code.startswith('INC'):
                return '45'          # incapacidades -> otros pagos
            if code == 'TRANS':
                return '45'          # auxilio de transporte -> otros pagos
            return '36'              # basico, horas extra, recargos, bonif. salarial, licencias

        return False

    @api.model
    def cert220_asignar_defecto(self):
        """(Re)asigna la casilla del 220 a TODAS las reglas segun el mapeo por defecto.
        Sobrescribe, para dejar una base limpia; luego se pueden ajustar casos puntuales."""
        for rule in self.search([]):
            rule.cert220_casilla = self._cert220_casilla_para(rule)
        return True
