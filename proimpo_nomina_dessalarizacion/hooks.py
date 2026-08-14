# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

FORMULA_SAL = (
    "result = payslip._proimpo_exceso_1393(\n"
    "    categories.get('BASIC', 0.0) + categories.get('DEVSAL', 0.0),\n"
    "    categories.get('DEVNOSAL', 0.0),\n"
    "    categories.get('BASIC', 0.0) + categories.get('DEVSAL', 0.0)\n"
    "    + categories.get('DEVNOSAL', 0.0) + categories.get('AUXT', 0.0),\n"
    ")"
)
# La contrapartida no salarial = -exceso (referencia el total ya calculado)
FORMULA_NS = "result = - RECLAS1393SAL"

# Regla IBC original (sin ajuste 1393: la reclasificacion ya lleva el exceso a DEVSAL)
FORMULA_IBC = (
    "smmlv = contract.company_id.smmlv_value\n"
    "dias = (payslip.date_to - payslip.date_from).days + 1\n"
    "base = categories.get('BASIC', 0) + categories.get('DEVSAL', 0)\n"
    "result = min(max(base, smmlv / 30.0 * min(dias, 30)), 25 * smmlv)"
)


def _cat(env, code):
    C = env['hr.salary.rule.category']
    return (C.search([('code', '=', code)], limit=1)
            or C.search([('code', 'ilike', code)], limit=1))


def post_init_hook(env):
    Rule = env['hr.salary.rule']
    Struct = env['hr.payroll.structure']

    devsal = _cat(env, 'DEVSAL')
    devnosal = _cat(env, 'DEVNOSAL')
    if not devsal or not devnosal:
        _logger.warning("PROIMPO des-salarizacion: faltan categorias DEVSAL/DEVNOSAL; reglas no creadas.")
        return

    nombre_est = env['ir.config_parameter'].sudo().get_param(
        'proimpo_nomina.estructura_devengados', 'Nomina Colombia Quincenal')
    structs = Struct.search([('name', '=', nombre_est)]) or Struct.search([('name', 'ilike', 'quincenal')])
    if not structs:
        _logger.warning("PROIMPO des-salarizacion: no se encontro estructura quincenal; reglas no creadas.")
        return

    reglas = [
        ('RECLAS1393SAL', 'Reclasificación 1393 (a salarial)', 110, devsal, FORMULA_SAL),
        ('RECLAS1393NS', 'Reclasificación 1393 (menos no salarial)', 111, devnosal, FORMULA_NS),
    ]
    for st in structs:
        for code, name, seq, cat, formula in reglas:
            r = Rule.search([('code', '=', code), ('struct_id', '=', st.id)], limit=1)
            vals = {
                'name': name, 'code': code, 'category_id': cat.id, 'struct_id': st.id,
                'sequence': seq, 'appears_on_payslip': True,
                'condition_select': 'none', 'amount_select': 'code',
                'amount_python_compute': formula,
            }
            if r:
                r.write(vals)
            else:
                Rule.create(vals)
        # Restaurar la regla IBC a su version original (la reclasificacion ya aporta el exceso)
        ibc = Rule.search([('code', '=', 'IBC'), ('struct_id', '=', st.id)], limit=1)
        if ibc:
            ibc.write({'amount_select': 'code', 'amount_python_compute': FORMULA_IBC})
    _logger.info("PROIMPO des-salarizacion: reglas RECLAS1393 aseguradas y regla IBC restaurada.")
