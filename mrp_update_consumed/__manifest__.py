# -*- coding: utf-8 -*-
{
    'name': "Actualiza cantidades consumidas",

    'summary': """
        Actualiza las cantidades consumidas con base en las transferencias
        """,

    'description': """
        Actualiza las cantidades consumidas desde las transferencias
    """,

    'author': "Doxoo S.A.S.",
    'website': "http://www.doxoo.co",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Manufacturing/Manufacturing',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['mrp'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/mrp_update_consumed_view.xml',
        #'views/views.xml',
        #'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
