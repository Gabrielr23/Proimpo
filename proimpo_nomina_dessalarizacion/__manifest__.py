# -*- coding: utf-8 -*-
{
    'name': 'PROIMPO Nómina - Des-salarización (Ley 1393)',
    'version': '18.0.1.0.1',
    'summary': 'Reclasifica en la 2Q el exceso no salarial (>40%) a salarial, para IBC + prestaciones + aportes',
    'description': """
Automatiza la des-salarización (método recomendado por asesoría jurídica): en la
segunda quincena calcula el exceso de pagos NO salariales sobre el 40% de la
remuneracion total del mes y lo RECLASIFICA a salarial, con dos lineas de ajuste:

  - RECLAS1393SAL  (Devengado salarial, +exceso)
  - RECLAS1393NS   (Devengado no salarial, -exceso)

El bruto no cambia; solo cambia la clasificacion, dejando lo no salarial en el 40%.
Al quedar en DEVSAL, el exceso entra a IBC, base de prestaciones y aportes por las
reglas normales. NO usar junto con proimpo_nomina_ibc (son excluyentes): este modulo
restaura la regla IBC original (BASIC + DEVSAL).
""",
    'author': 'Proimpo SAS',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
