# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - PILA (generador del archivo)",
    'summary': "Campos de seguridad social (EPS, AFP, ARL, Caja) en el contrato para la PILA",
    'description': "Fase 1 de la PILA: agrega al contrato los campos de entidades (EPS, AFP, ARL, Caja de Compensación) y municipio de labor que exige la planilla (Resolución 2388/2016). El generador del archivo se construye en la Fase 2.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': '19.0.2.3.6',
    'depends': ['l10n_co_hr_payroll_enterprise', 'proimpo_nomina_liquidacion'],
    'data': [
        'views/hr_contract_views.xml',
        'views/pila_reporte_views.xml',
        'views/pila_plano_views.xml',
        'views/hr_leave_type_views.xml',
    ],
    'installable': True,
    'application': False,
}
