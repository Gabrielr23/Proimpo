# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Valor hora automático en novedades",
    'summary': "Calcula el Importe por hora de horas extra y recargos desde el salario del contrato",
    'description': """
Al seleccionar un concepto de hora extra o recargo en los devengados del recibo,
llena automáticamente el Importe = (salario del contrato / divisor) x factor.
El usuario solo digita la cantidad de horas (o el rango de horas).
Divisor: 220 (jornada 44h) hasta el 14-jul-2026; 210 (jornada 42h) desde el 15-jul-2026.
Recargo dominical/festivo date-aware: 75%/80%/90%/100% (Ley 2466/2025).
    """,
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': '18.0.1.1.0',
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'installable': True,
    'application': False,
}
