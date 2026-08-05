# -*- coding: utf-8 -*-
{
    'name': 'PROIMPO Nómina - IBC Ley 1393',
    'version': '18.0.1.0.0',
    'summary': 'Aplica el límite del 40% (Ley 1393/2010) al IBC real de seguridad social',
    'description': """
Lleva el exceso de pagos NO salariales sobre el 40% de la remuneración total
al IBC real (salud, pensión, FSP del empleado, aportes patronales y PILA).

- Fórmula: exceso = max(no_salarial - 0.40 * (salarial + no_salarial), 0)
- No salarial = categoría DEVNOSAL (el auxilio de transporte ya está aparte en AUXT).
- Reconciliación MENSUAL aplicada en la 2Q: la 2Q calcula el exceso del mes
  completo (1Q + 2Q) y lo suma a su IBC; la 1Q va sin ajuste. Así la suma de
  las dos quincenas = IBC mensual correcto para PILA.
""",
    'author': 'Proimpo SAS',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
