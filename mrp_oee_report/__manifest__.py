# -*- coding: utf-8 -*-
{
    'name': 'OEE por Turno y Tablero OEE',
    'version': '18.0.1.3.0',
    'summary': 'OEE con cascada de minutos (paradas autorizadas, no programadas, '
               'velocidad y calidad) y tablero de planta.',
    'description': """
OEE por Turno y Tablero OEE
===========================

Modelo de minutos (igual al tablero de Access de planta): D = operando / cargado;
R = minutos estándar de lo producido / minutos operando; C = buenas / producidas;
OEE = D x R x C.

* Cada línea de tiempo se reparte entre los turnos del calendario que atraviesa.
* Una línea de más de 12 h no cuenta y pasa a Calidad del registro.
* El reloj de la máquina se cuenta una vez (salvo CT de la lista paralela).
* Estándar: ciclo actual del molde, si no el teórico, si no el de la operación.
* Paradas autorizadas: casilla en el catálogo de motivos de pérdida.
* Datos en tabla actualizada por partes: cada 15 min y con Actualizar se
  recalculan solo los últimos 3 días; actualizar el módulo no recalcula nada
  salvo que cambie el cálculo (entonces el histórico se rehace en segundo plano).
* Botón Recalcular periodo para correcciones más antiguas.
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
        'data/oee_params.xml',
        'data/oee_data.xml',
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
