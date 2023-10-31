# -*- coding: utf-8 -*-
from odoo import http

# class ControlCreditLimit(http.Controller):
#     @http.route('/control_credit_limit/control_credit_limit/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/control_credit_limit/control_credit_limit/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('control_credit_limit.listing', {
#             'root': '/control_credit_limit/control_credit_limit',
#             'objects': http.request.env['control_credit_limit.control_credit_limit'].search([]),
#         })

#     @http.route('/control_credit_limit/control_credit_limit/objects/<model("control_credit_limit.control_credit_limit"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('control_credit_limit.object', {
#             'object': obj
#         })