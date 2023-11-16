# -*- coding: utf-8 -*-
# from odoo import http


# class MrpUpdateQuantitiesConsumed(http.Controller):
#     @http.route('/mrp_update_quantities_consumed/mrp_update_quantities_consumed', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/mrp_update_quantities_consumed/mrp_update_quantities_consumed/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('mrp_update_quantities_consumed.listing', {
#             'root': '/mrp_update_quantities_consumed/mrp_update_quantities_consumed',
#             'objects': http.request.env['mrp_update_quantities_consumed.mrp_update_quantities_consumed'].search([]),
#         })

#     @http.route('/mrp_update_quantities_consumed/mrp_update_quantities_consumed/objects/<model("mrp_update_quantities_consumed.mrp_update_quantities_consumed"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('mrp_update_quantities_consumed.object', {
#             'object': obj
#         })
