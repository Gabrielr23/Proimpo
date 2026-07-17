# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Consignacion anual de cesantias",
    'summary': "Genera el plano de consignacion de cesantias al fondo (Aportes en Linea) + reporte",
    'description': "Recalcula las cesantias al 31 de diciembre (base x dias/360) por empleado "
                   "activo, agrupa por fondo de cesantias y genera el archivo plano para cargue "
                   "en Aportes en Linea, mas un reporte de control (recalculo vs provision).",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "18.0.1.4.2",
    'depends': ['l10n_co_hr_payroll_enterprise', 'proimpo_nomina_liquidacion'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_contract_views.xml',
        'views/cesantias_views.xml',
    ],
    'installable': True,
    'application': False,
}
