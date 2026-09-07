# -*- coding: utf-8 -*-
{
    'name': "Actualiza cantidades Consumidas en MRP",

    'summary': """
        Actualiza las cantidades consumidas con base en las transferencias
        """,

    'description': """
        Actualiza las cantidades consumidas con base en las transferencias
    """,

    'author': "Doxoo S.A.S.",
    'website': "http://www.doxoo.co",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Manufacturing/Manufacturing',
    'version': '19.0.1.0.0',

    # MIGRACION 19.0: se agrega 'license' (Odoo 19 emite un WARNING en el log
    # cuando falta y asume LGPL-3).
    'license': 'LGPL-3',

    # MIGRACION 19.0: se agrega 'stock_account'. El modulo filtra por
    # stock.move.to_refund, campo que NO esta definido en 'stock' ni en 'mrp'
    # sino en 'stock_account' (addons/stock_account/models/stock_move.py).
    # 'mrp' declara depends = ['product', 'stock', 'resource'], asi que la
    # dependencia no estaba garantizada.
    'depends': ['mrp', 'stock_account'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/mrp_update_consumed_view.xml',
        'views/stock_picking.xml',
        'views/stock_picking_type.xml',
    ],
    'installable': True,
}
