# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Liquidación de contratos",
    'summary': "Liquidación definitiva: prestaciones proporcionales, vacaciones e indemnización",
    'description': """
Métodos para liquidación definitiva de contratos (recibo independiente):
 - Promedio salarial del último año (fijo + variables: extras, recargos, comisiones,
   bonos salariales), dividido por los meses efectivamente laborados (excluye meses de
   suspensión sin devengo), como lo establece la ley.
 - Cesantías, intereses a las cesantías, prima de servicios y vacaciones proporcionales,
   con días comerciales (base 360).
 - Indemnización automática por despido sin justa causa según el tipo de contrato
   (indefinido: tabla Art. 64; término fijo: salarios faltantes; obra: mínimo 15 días).
    """,
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "18.0.1.0.1",
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'data': [],
    'installable': True,
    'application': False,
}
