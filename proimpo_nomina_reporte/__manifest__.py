# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Reporte columnar de nómina",
    'summary': "Exporta a Excel una matriz empleado x concepto del lote (revisión)",
    'description': "Genera un Excel columnar (un empleado por fila, cada concepto en columna) desde el lote de nómina, para revisión rápida de la quincena.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': '18.0.1.2.0',
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'data': ['views/hr_payslip_run_views.xml'],
    'installable': True,
    'application': False,
}
