# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Nueva formula de la regla IBC: delega en el helper que aplica la Ley 1393.
# 'payslip' y 'categories' estan disponibles en el contexto de la regla salarial.
IBC_FORMULA = (
    "result = payslip._proimpo_ibc_1393(\n"
    "    categories.get('BASIC', 0.0) + categories.get('DEVSAL', 0.0),\n"
    "    categories.get('DEVNOSAL', 0.0),\n"
    ")"
)


def post_init_hook(env):
    """Actualiza la(s) regla(s) con codigo IBC para que calculen el IBC con el
    limite del 40% (Ley 1393). Guarda la formula anterior en una nota por si se
    requiere revertir."""
    rules = env['hr.salary.rule'].search([('code', '=', 'IBC')])
    if not rules:
        _logger.warning("PROIMPO IBC 1393: no se encontro ninguna regla con codigo 'IBC'.")
        return
    for rule in rules:
        anterior = rule.amount_python_compute or ''
        if 'result = payslip._proimpo_ibc_1393(' in anterior:
            continue  # ya aplicado (idempotente)
        rule.write({
            'amount_select': 'code',
            'amount_python_compute': IBC_FORMULA,
            'note': (rule.note or '') + "\n[PROIMPO 1393] Formula anterior:\n" + anterior,
        })
        _logger.info("PROIMPO IBC 1393: regla IBC (id %s) actualizada.", rule.id)
