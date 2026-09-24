# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpAveriaCategoria(models.Model):
    """Catalogo de categorias de averia para la hoja de trabajo
    unificada "Registro Averías" (Fase 4).

    Reemplaza el campo de seleccion fijo que hoy tienen las hojas de
    trabajo de Studio (confirmado por Laura: hoy es un campo
    Selection, no un Many2one). Las categorias existentes se recrean
    aqui como datos (ver data/mrp_averia_categoria_data.xml) -- ninguna
    se borra ni se renombra, solo se les agrega el tipo de Centro de
    Trabajo al que aplican.

    PENDIENTE: Laura mencionó que iba a adjuntar la lista real de
    categorías (con el mismo criterio "estas también se pueden
    modificar" que usó para las Razones de pérdida) pero el archivo no
    llegó en el mensaje -- por ahora data/mrp_averia_categoria_data.xml
    no trae categorías reales, solo el mecanismo. En cuanto llegue el
    archivo se carga igual que se hizo con las ~91 razones de pérdida.
    """
    _name = 'mrp.averia.categoria'
    _description = "Categoría de avería"
    _order = 'name'

    name = fields.Char(required=True)
    tipo_centro_trabajo = fields.Selection([
        ('inyectoras', "Inyectoras"),
        ('sopladoras', "Sopladoras"),
        ('impresion', "Impresión"),
        ('sellado', "Sellado"),
    ], string="Tipo de Centro de Trabajo",
        help="Si se deja vacío, la categoría aplica a todos los tipos "
             "de Centro de Trabajo.")
    active = fields.Boolean(default=True)
