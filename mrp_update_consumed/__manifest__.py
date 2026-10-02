# -*- coding: utf-8 -*-
{
    'name': "Actualiza cantidades Consumidas en MRP",
    'summary': "Calcula la Cantidad hecha de los componentes desde lo enviado "
               "con Pick Components (Pre-Production o talleres), descontando "
               "devoluciones, desechos y lo ya consumido.",
    'description': """
Odoo 19 - mismas reglas que la v0.8 de Odoo 18.

Disponible = enviado con Pick Components (a Pre-Production o a un taller)
menos devoluciones, menos desechos de las órdenes del grupo, menos lo ya
consumido en cierres anteriores.

Cierre parcial: proporción de la lista de materiales, con tope en lo
disponible. Cierre final o "Sin backorder": todo lo disponible. Nunca
negativo. Requiere "Transferido totalmente" en el último envío.
    """,
    'author': "Doxoo S.A.S.",
    'website': "http://www.doxoo.co",
    'category': 'Manufacturing/Manufacturing',
    'version': '19.0.1.1.0',
    'depends': ['mrp'],
    'data': [
        'views/mrp_update_consumed_view.xml',
        'views/stock_picking.xml',
        'views/stock_picking_type.xml',
        'views/mrp_production_actions.xml',
    ],
    'license': 'LGPL-3',
}
