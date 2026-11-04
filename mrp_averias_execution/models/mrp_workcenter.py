# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpWorkcenter(models.Model):
    """Fases 4 y 5: agrega el tipo de Centro de Trabajo que se usa para
    filtrar tanto las categorias de averia de la hoja de trabajo
    (mrp.averia.categoria) como el catalogo de Razones de perdida
    (mrp.workcenter.productivity.loss).

    Confirmado en vivo con Laura (24/09): todos los Centros de Trabajo
    ya tienen etiquetas nativas en el campo `tag_ids` de `mrp.workcenter`
    (modelo relacionado con un campo `name`). Por eso este campo ya NO
    es de seleccion manual: se calcula solo, buscando (ilike, via
    filtered/contains sobre el nombre en minusculas) una etiqueta cuyo
    nombre coincida con cada tipo. No requiere marcar nada Centro de
    Trabajo por Centro de Trabajo -- si un CT queda sin tipo es porque
    ninguna de sus etiquetas coincide con los 4 grupos conocidos.
    """
    _inherit = 'mrp.workcenter'

    # (valor del selection, etiqueta visible, texto a buscar con ilike
    # dentro del nombre de cada etiqueta de tag_ids)
    _TIPOS_CENTRO_TRABAJO = [
        ('inyectoras', "Inyectoras", 'inyector'),
        ('sopladoras', "Sopladoras", 'soplador'),
        ('impresion', "Impresión", 'impres'),
        ('sellado', "Sellado", 'sellado'),
    ]

    tipo_centro_trabajo = fields.Selection(
        [(valor, etiqueta) for valor, etiqueta, _texto in _TIPOS_CENTRO_TRABAJO],
        string="Tipo de Centro de Trabajo",
        compute='_compute_tipo_centro_trabajo',
        store=True,
        help="Calculado automáticamente a partir de las etiquetas "
             "(tag_ids) del Centro de Trabajo. Determina qué categorías "
             "de avería y qué razones de pérdida se muestran para las "
             "órdenes de este Centro de Trabajo. Un Centro de Trabajo "
             "sin ninguna etiqueta reconocida queda sin tipo y solo ve "
             "las categorías/razones que aplican a todos los tipos.")

    @api.depends('tag_ids.name')
    def _compute_tipo_centro_trabajo(self):
        for workcenter in self:
            tipo = False
            for valor, _etiqueta, texto in self._TIPOS_CENTRO_TRABAJO:
                coincide = workcenter.tag_ids.filtered(
                    lambda tag, texto=texto: texto in (tag.name or '').lower()
                )
                if coincide:
                    tipo = valor
                    break
            workcenter.tipo_centro_trabajo = tipo
