# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# (codigo, nombre, secuencia, tipos de prestamo que agrupa)
REGLAS = [
    ('LIBR', 'Libranzas', 320, ('libranza',)),
    ('PREST', 'Préstamos y otros descuentos', 324, ('prestamo', 'otro')),
]


def _formula(tipos):
    tipos_py = repr(tuple(tipos))
    return (
        "result = - sum(\n"
        "    l.get_installment_for_date(payslip.date_to, payslip)\n"
        "    for l in employee.loan_ids\n"
        "    if l.loan_type in %s\n"
        ")" % tipos_py
    )


def post_init_hook(env):
    """Crea (o actualiza) las reglas de deduccion LIBR y PREST en la(s) estructura(s)
    quincenal(es), para que la cuota del prestamo se descuente en el recibo."""
    Rule = env['hr.salary.rule']
    Cat = env['hr.salary.rule.category']
    Struct = env['hr.payroll.structure']

    ded = (Cat.search([('code', '=', 'DED')], limit=1)
           or Cat.search([('code', 'ilike', 'ded')], limit=1)
           or Cat.search([('name', 'ilike', 'deduc')], limit=1))
    if not ded:
        _logger.warning("PROIMPO prestamos: no se encontro categoria de Deduccion; reglas no creadas.")
        return

    nombre_est = env['ir.config_parameter'].sudo().get_param(
        'proimpo_nomina.estructura_deducciones', 'Nomina Colombia Quincenal')
    structs = Struct.search([('name', '=', nombre_est)]) or Struct.search([('name', 'ilike', 'quincenal')])
    if not structs:
        _logger.warning("PROIMPO prestamos: no se encontro estructura '%s' ni 'quincenal'; "
                        "cree las reglas LIBR/PREST manualmente.", nombre_est)
        return

    n = 0
    for st in structs:
        for code, name, seq, tipos in REGLAS:
            formula = _formula(tipos)
            rule = Rule.search([('code', '=', code), ('struct_id', '=', st.id)], limit=1)
            vals = {
                'name': name,
                'code': code,
                'category_id': ded.id,
                'struct_id': st.id,
                'sequence': seq,
                'appears_on_payslip': True,
                'condition_select': 'none',
                'amount_select': 'code',
                'amount_python_compute': formula,
            }
            if rule:
                rule.write({'amount_select': 'code', 'amount_python_compute': formula,
                            'category_id': ded.id, 'appears_on_payslip': True})
            else:
                Rule.create(vals)
                n += 1
    _logger.info("PROIMPO prestamos: reglas LIBR/PREST aseguradas en %s estructura(s) (%s creadas).",
                 len(structs), n)
