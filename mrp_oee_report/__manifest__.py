# -*- coding: utf-8 -*-
{
    'name': 'OEE por Turno y Tablero OEE',
    'version': '18.0.1.1.0',
    'summary': 'OEE con cascada de minutos (paradas autorizadas, no programadas, '
               'velocidad y calidad) y tablero de planta.',
    'description': """
OEE por Turno y Tablero OEE
===========================

Modelo de minutos, igual al tablero de Access de planta:

  registrado = operando + paradas autorizadas + paradas no programadas
  cargado    = registrado - paradas autorizadas
  D = operando / cargado
  R = minutos estándar de lo producido / minutos operando (con estándar)
  C = buenas / (buenas + averías)
  OEE = D x R x C

- Paradas autorizadas: casilla en el catálogo de motivos de pérdida.
- Estándar: ciclo TEÓRICO del molde / cavidades; si no hay molde, el ciclo
  manual de la operación.
- Los % se calculan siempre sobre sumas de minutos (nunca promediando %).
- Meta y semáforo: oee_target del centro de trabajo (verde >= meta,
  amarillo hasta 10 puntos debajo, rojo más abajo).

Las columnas de turnos, moldes y operario se verifican al crear la vista
(si una falta, el informe funciona con menos detalle y lo deja en el log).
Tras actualizar turnos o moldes: Acciones > Regenerar informe de OEE.
""",
    'author': 'PROIMPO S.A.S.',
    'category': 'Manufacturing',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'mrp_shift_resolver',
        'mrp_mold_management',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_oee_report_views.xml',
        'data/menu_placement.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mrp_oee_report/static/src/dashboard/oee_dashboard.js',
            'mrp_oee_report/static/src/dashboard/oee_dashboard.xml',
            'mrp_oee_report/static/src/dashboard/oee_dashboard.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
