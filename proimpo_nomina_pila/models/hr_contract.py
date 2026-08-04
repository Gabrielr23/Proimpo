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
    pila_fecha_productiva = fields.Date(
        string="Fecha inicio etapa productiva",
        help="Día en que el aprendiz pasa de lectiva a productiva. Si el cambio cae a mitad de "
             "quincena, se generan dos recibos: uno lectiva (hasta el día anterior) y uno productiva "
             "(desde esta fecha).")
    pila_etapa_aprendiz = fields.Selection(
        [('lectiva', 'Lectiva'), ('productiva', 'Productiva')],
        string="Etapa (aprendiz)",
        help="Solo para contratos de aprendizaje (Ley 2466/2025). Lectiva: apoyo 75%% SMMLV, solo salud y ARL a cargo de la empresa (usar estructura Aprendiz Lectiva). Productiva: apoyo 100%% SMMLV con seguridad social y prestaciones plenas (estructura normal). En ambas etapas NO aplican parafiscales.")
    pila_pensionado = fields.Boolean(
        string="Pensionado (no cotiza a pensión)",
        help="Marcar si el trabajador ya está pensionado. En ese caso NO se calculan "
             "los aportes a pensión (empleado y empleador) ni el FSP; salud, ARL y "
             "parafiscales siguen aplicando.")
    pila_municipio_code = fields.Char(
        string="Municipio de labor (DANE)",
        help="Código DANE departamento+municipio donde labora (5 dígitos, ej. 76001 Cali).")
    pila_arl_class = fields.Selection(
        [('1', '01 - Riesgo minimo 0.522%'), ('2', '02 - Riesgo bajo 1.044%'),
         ('3', '03 - Tarifa 0%'), ('4', '04 - Riesgo alto 4.350%'),
         ('5', '05 - Centro 2.436% alto')],
        string="Centro de trabajo (ARL)", default='5',
        help="Centro de trabajo ARL segun CGUNO/Aportes (codigo 01-05). Determina la "
             "tarifa de riesgo en la PILA (pos 398). Distinto del codigo de sucursal de 7 digitos.")
    pila_centro_trabajo = fields.Char(
        string="Centro de trabajo PILA",
        help="Codigo de centro de trabajo/actividad para la PILA (pos 687-693). "
             "Si se deja vacio se usa el valor por defecto de la compania.")
