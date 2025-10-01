# -*- encoding: utf-8 -*-
{
    "name": "Nómina - Vacaciones",
    "version": "18.0.0.1",
    "description": """
Permite calcular los días de vacaciones disponible de un empleado con base en la fecha de ingreso y las ausencias por vacaciones
    """,
    'author': 'DOXOO S.A.S',
    "category": "Generic Modules/Human Resources",
    "depends": [
		    "hr_contract", "hr","hr_holidays","hr_payroll_co",
			],
	"data":[
        'data/paperformat.xml',
        'data/hr_rule_parameters_data.xml',
        'data/hr_payslip_input_type_data.xml',
        'views/hr_employee_view.xml',
        'views/hr_salary_rule_view.xml',
        'views/hr_payslip_input_type_view.xml',
        'views/hr_leave_type_view.xml',
        'views/hr_previous_payrolls_view.xml',
        'views/hr_liquidation_consolidated_view.xml',
        'views/hr_payslip_view.xml',
        'views/hr_contract_view.xml',
        'views/hr_contract_liquidation_view.xml',
        'wizard/create_novedades_wizard_view.xml',
        'wizard/create_novedades_consolidated_wizard_view.xml',
        'reports/contract_liquidation_only_document.xml',
        'reports/contract_liquidation_payslip_document.xml',
        'security/ir.model.access.csv',
			],
    "demo_xml": [
			],
    'images': [
            '/static/description/icon.png'
            ],            
    'auto_install': False,
    "installable": True,
    "certificate" : "",
    'license': 'Other proprietary',
    
}

