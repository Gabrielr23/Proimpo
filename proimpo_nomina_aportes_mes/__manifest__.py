# -*- coding: utf-8 -*-
{
    'name': 'PROIMPO Nómina - Aportes con umbral mensual',
    'version': '18.0.1.1.0',
    'summary': 'FSP (tramo), SENA, ICBF y exoneración evaluados sobre el IBC del MES (reconciliado en la 2Q)',
    'description': """
Los aportes con UMBRAL o TRAMO no son lineales: al partir el mes en dos quincenas,
cada quincena puede quedar por debajo del umbral aunque el mes lo supere. Este módulo
los evalúa sobre el IBC del MES (leyendo la 1Q) y reconcilia en la 2Q:

  - FSP: el tramo (1%..2%, incluye el adicional > 16 SMMLV) según el IBC del mes.
  - SENA / ICBF: exoneración (Art. 114-1) según el IBC del mes (>= 10 SMMLV).

Incluye la acción "Re-aplicar reglas PROIMPO" (en la lista de Reglas salariales) para
dejar IBC, base de prestaciones, FSP, SENA e ICBF con la fórmula correcta sin editar a
mano ni reinstalar.
""",
    'author': 'Proimpo SAS',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'data': ['data/actions.xml'],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
