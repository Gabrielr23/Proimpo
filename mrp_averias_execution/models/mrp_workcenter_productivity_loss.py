# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpWorkcenterProductivityLoss(models.Model):
    """Fase 5: extiende el catálogo nativo de Razones de pérdida para
    poder filtrarlo por tipo de Centro de Trabajo en el campo loss_id
    del Seguimiento de tiempo (ver mrp_workcenter_productivity.py).

    es_programada: confirmado con Laura que no existe un campo nativo
    equivalente a la columna "Programada / No programada" del archivo
    que compartió -- por eso se agrega aquí.

    Los datos se cargan desde
    data/mrp_workcenter_productivity_loss_data.xml, con noupdate="1"
    para que Laura pueda editarlos libremente desde Configuración ->
    Pérdidas de productividad sin que una actualización del módulo se
    los pise (confirmado que ella los quiere poder ajustar).
    """
    _inherit = 'mrp.workcenter.productivity.loss'

    tipo_centro_trabajo = fields.Selection([
        ('inyectoras', "Inyectoras"),
        ('sopladoras', "Sopladoras"),
        ('impresion', "Impresión"),
        ('sellado', "Sellado"),
    ], string="Tipo de Centro de Trabajo",
        help="Si se deja vacío, la razón aplica a todos los tipos de "
             "Centro de Trabajo (por ejemplo, paradas periféricas / "
             "servicios críticos).")
    es_programada = fields.Boolean(
        string="Programada",
        help="Parada programada (setup, cambio de molde, etc.) vs. no "
             "programada (falla, falta de material, etc.).")
