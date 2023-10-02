##############################################################################
#
# Copyright (c) 2022 INNOVATECSA S.A.S - (http://www.innovatecsa.com).
#
##############################################################################
{
    'name': 'Nómina Colombiana',
    'version': '15.0',
    'author': 'DOXOO S.A.S',
    'category': 'Generic Modules/Human Resources',
    'depends': [
        'hr',
        'hr_contract',
        'hr_holidays',
        'hr_payroll',
        'hr_payroll_account',
    ],
    'demo': [],
    'description': """
Módulo de nomina para la localizacion colombiana

    """,
    'data': [
	   'views/hr_rule_parameter_view.xml',
	   'views/hr_contract_view.xml',
       'views/hr_salary_rule_view.xml',
       'views/hr_payslip_view.xml',
       'security/ir.model.access.csv',
	   'views/hr_novedades_view.xml',
	   'data/hr_payroll_data.xml',
    ],
    'images': [
            '/static/description/icon.png'
],
    'auto_install': False,
    'installable': True,
    'images': [],
    'license': 'Other proprietary',

}

