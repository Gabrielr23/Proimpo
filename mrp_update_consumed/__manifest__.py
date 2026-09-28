# -*- coding: utf-8 -*-
{
    'name': "Actualiza cantidades Consumidas en MRP",
    'summary': "Calcula la cantidad consumida de cada componente a partir de lo "
               "realmente transferido a pre-producción (Pick Components), "
               "descontando devoluciones, desechos y lo ya consumido.",
    'description': """
Reescritura para Odoo 19.

Cantidad hecha de cada componente de la orden de fabricación = transferido a
pre-producción (Pick Components) menos lo devuelto desde pre-producción, menos
lo desechado desde la orden, menos lo ya consumido por órdenes anteriores del
mismo grupo (backorders).

Solo se calcula cuando la última transferencia recibida del componente
tiene marcado "Transferido totalmente"; si no, la Cantidad hecha es 0.

Se recalcula al cambiar la Cantidad de la orden, al validar un Pick
Components o una devolución, al marcar "Transferido totalmente", al
validar un desecho, al producir (para el backorder) y con el botón
"Recalcular consumo".
    """,
    'author': "Doxoo S.A.S.",
    'website': "http://www.doxoo.co",
    'category': 'Manufacturing/Manufacturing',
    'version': '19.0.1.0.0',
    'depends': ['mrp'],
    'data': [
        'views/mrp_update_consumed_view.xml',
        'views/stock_picking.xml',
        'views/stock_picking_type.xml',
        'views/mrp_production_actions.xml',
    ],
    'license': 'LGPL-3',
}
