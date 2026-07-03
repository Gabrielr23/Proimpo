# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Archivo plano Bancolombia",
    'summary': "Genera el archivo de pago de nómina para cargue en Bancolombia",
    'description': "Genera el archivo plano de dispersión de pagos de nómina para Bancolombia desde un lote de recibos.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "18.0.1.0.0",
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'data': [
        'data/params.xml',
        'views/hr_payslip_views.xml',
        'views/res_partner_bank_views.xml',
    ],
    'installable': True,
    'application': False,
}
