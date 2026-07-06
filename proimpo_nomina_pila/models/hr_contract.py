# -*- coding: utf-8 -*-
from odoo import models, fields


class HrContract(models.Model):
    _inherit = 'hr.contract'

    pila_eps_code = fields.Char(
        string="Código EPS (salud)",
        help="Código de la EPS según Resolución 2388 (ej. EPS037 Nueva EPS, EPS005 Sanitas).")
    pila_afp_code = fields.Char(
        string="Código AFP (pensión)",
        help="Código de la administradora de pensiones (ej. 230301 Porvenir, 231001 Protección).")
    pila_arl_code = fields.Char(
        string="Código ARL",
        help="Código de la ARL a la que está afiliado el trabajador.")
    pila_ccf_code = fields.Char(
        string="Código Caja de Compensación",
        help="Código de la Caja de Compensación Familiar (ej. CCF57 Comfandi).")
    pila_municipio_code = fields.Char(
        string="Municipio de labor (DANE)",
        help="Código DANE departamento+municipio donde labora (5 dígitos, ej. 76001 Cali).")
