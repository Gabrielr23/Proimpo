# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# (codigo, nombre, casilla 220, campo del contrato)
REGLAS = [
    ('AFC', 'Aporte AFC', '54', 'x_studio_aportes_afc'),
    ('PENSVOL', 'Aporte pension voluntaria', '53', 'x_studio_aporte_fondo_voluntario_de_pensiones'),
]


def post_init_hook(env):
    """Crea las reglas de deduccion AFC y pension voluntaria en la(s) estructura(s) quincenal(es)."""
    Rule = env['hr.salary.rule']
    Cat = env['hr.salary.rule.category']
    Struct = env['hr.payroll.structure']

    ded = (Cat.search([('code', '=', 'DED')], limit=1)
           or Cat.search([('code', 'ilike', 'ded')], limit=1)
           or Cat.search([('name', 'ilike', 'deduc')], limit=1))
    if not ded:
        _logger.warning("PROIMPO aportes: no se encontro categoria de Deduccion; no se crean reglas.")
        return

    nombre_est = env['ir.config_parameter'].sudo().get_param(
        'proimpo_nomina.estructura_deducciones', 'Nomina Colombia Quincenal')
    structs = Struct.search([('name', '=', nombre_est)]) or Struct.search([('name', 'ilike', 'quincenal')])
    if not structs:
        _logger.warning("PROIMPO aportes: no se encontro estructura '%s' ni ninguna 'quincenal'; "
                        "cree las reglas manualmente o ajuste el parametro "
                        "proimpo_nomina.estructura_deducciones.", nombre_est)
        return

    creadas = 0
    for st in structs:
        for code, name, casilla, campo in REGLAS:
            if Rule.search([('code', '=', code), ('struct_id', '=', st.id)], limit=1):
                continue
            vals = {
                'name': name,
                'code': code,
                'category_id': ded.id,
                'struct_id': st.id,
                'sequence': 200,
                'appears_on_payslip': True,
                'condition_select': 'python',
                'condition_python': "result = bool(getattr(contract, '%s', 0))" % campo,
                'amount_select': 'code',
                'amount_python': "result = -(getattr(contract, '%s', 0) or 0.0) / 2.0" % campo,
            }
            if 'cert220_casilla' in Rule._fields:
                vals['cert220_casilla'] = casilla
            Rule.create(vals)
            creadas += 1
    _logger.info("PROIMPO aportes: %s regla(s) creada(s) en %s estructura(s).", creadas, len(structs))
