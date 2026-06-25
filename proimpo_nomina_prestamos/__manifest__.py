# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Préstamos y Libranzas",
    'summary': "Control de préstamos, libranzas y descuentos con saldos en nómina",
    'description': """
Gestiona los préstamos, libranzas y otros descuentos por empleado, con control
automático de saldos:
- Un empleado puede tener uno o varios préstamos/libranzas a la vez.
- Cada nómina descuenta la cuota, reduce el saldo y se detiene al llegar a cero.
- Las reglas de deducción LIBR (libranzas) y PREST (préstamos) leen los saldos activos.
- Al poner el recibo en borrador o cancelarlo, se reversa el abono (saldo restaurado).
    """,
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "18.0.1.0.0",
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_loan_views.xml',
    ],
    'installable': True,
    'application': False,
}
