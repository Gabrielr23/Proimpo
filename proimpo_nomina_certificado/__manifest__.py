# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Certificado de ingresos y retenciones (F220)",
    'summary': "Genera el Certificado de Ingresos y Retenciones (formato 220 DIAN) por empleado y ano",
    'description': "Consolida los pagos del ano por empleado y los mapea a las casillas del "
                   "formato 220 de la DIAN. Genera PDF individual por empleado y Excel de control. "
                   "Las cesantias consignadas (casilla 47) se toman del recalculo anual.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "18.0.1.3.2",
    'depends': ['l10n_co_hr_payroll_enterprise', 'proimpo_nomina_liquidacion'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_salary_rule_views.xml',
        'report/certificado_report.xml',
        'report/certificado_templates.xml',
        'views/certificado_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}
