# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Volante de pago",
    'summary': "Comprobante de pago compacto (nómina, vacaciones, liquidación) y envío por correo",
    'description': "Volante de pago de una página, con envío individual y masivo por correo al empleado.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': '18.0.1.3.3',
    'depends': ['l10n_co_hr_payroll_enterprise', 'mail'],
    'data': [
        'report/volante_report.xml',
        'data/mail_template.xml',
        'views/hr_payslip_views.xml',
    ],
    'installable': True,
    'application': False,
}
