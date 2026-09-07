{
    'name': "Generar Archivos Bancos Colombia",
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'description': """
        Generar archivos planos para bancos Colombia
    """,
    'author': 'DOXOO S.A.S.',
    'company': 'DOXOO S.A.S.',
    'maintainer': 'DOXOO S.A.S.',
    'website': "http://www.doxoo.co",
    'depends': ['account_payment'],
    # MIGRACION 19.0: se reordena 'data'. security/security.xml define
    # generate_bank_file.group_enable_pay, que views/account_payment_view.xml
    # referencia en un <attribute name="groups">. Cargando las vistas primero,
    # una instalacion limpia no podia resolver ese xmlid.
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/account_payment_view.xml',
        'views/res_bank_parameter_view.xml',
        'wizards/generate_bank_file_wizard_views.xml',
    ],
    'license': 'LGPL-3',
    'images': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
