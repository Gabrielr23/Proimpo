# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Contabilizacion de nomina por centro de costo",
    'summary': "La cuenta contable del asiento de nomina cambia segun el area (cuenta analitica)",
    'description': "Permite que la misma regla salarial contabilice en cuentas distintas segun el "
                   "area/centro de costo del contrato (Admin 5105, Ventas 5205, Operarios 7201, "
                   "Admon Produccion 7301). Campo Area en la cuenta analitica + tabla de mapeo "
                   "(regla x area -> cuenta) + override del asiento de nomina.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "18.0.1.0.0",
    'depends': ['hr_payroll_account', 'analytic'],
    'data': [
        'security/ir.model.access.csv',
        'views/proimpo_cuenta_mapeo_views.xml',
        'views/account_analytic_account_views.xml',
    ],
    'installable': True,
    'application': False,
}
