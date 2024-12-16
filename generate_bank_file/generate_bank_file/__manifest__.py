{
    'name': "Generar Archivos Bancos Colombia",
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'description': """
        Generar archivos planos para bancos Colombia
    """,
    'author': 'DOXOO S.A.S.',
    'company': 'DOXOO S.A.S.',
    'maintainer': 'DOXOO S.A.S.',
    'website': "http://www.doxoo.co",
    'depends': ['account_payment'],
    'data': [
        'security/security.xml',
        'views/res_bank_parameter_view.xml',
        'views/account_payment_view.xml',
        'wizards/generate_bank_file_wizard_views.xml',
        'security/ir.model.access.csv',
        
    ],
    'license': 'LGPL-3',
    'images': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
