# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Cierre mensual de prestaciones",
    'summary': "Consolidado de prestaciones a la fecha (recalculo) vs provision, con ajuste",
    'description': "Recalcula el consolidado real de cesantias, intereses, prima y vacaciones a "
                   "la fecha de corte (base = ultimo basico + promedio de variables), lo compara "
                   "contra la provision contabilizada y muestra el ajuste. Base para dejar las "
                   "provisiones al dia cada fin de mes.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "18.0.1.2.0",
    'depends': ['l10n_co_hr_payroll_enterprise', 'proimpo_nomina_liquidacion'],
    'data': ['views/cierre_prestaciones_views.xml'],
    'installable': True,
    'application': False,
}
