{
    'name': "Generar Archivos Bancos Colombia",
    'description': """
        Generar archivos planos para bancos Colombia
    """,
    'author': 'DOXOO S.A.S.',
    'website': "http://www.doxoo.co",
    'category': 'Accounting',
    'version': "15.0.1.0.0",
    'depends': ['account_payment'],
    'license': 'LGPL-3',
    'images': [
    ],
    'installable': True,
    'data': [
        'security/security.xml',
        'views/res_bank_parameter_view.xml',
        'views/account_payment_view.xml',
        'wizards/generate_bank_file_wizard_views.xml',
        'security/ir.model.access.csv',
        
    ],
    'demo': [
    ],
}
