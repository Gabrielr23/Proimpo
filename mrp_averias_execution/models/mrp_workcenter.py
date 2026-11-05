# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .mrp_workcenter_tipo import opciones_tipo_ct


class MrpWorkcenter(models.Model):
    """Fases 4 y 5: agrega el tipo de Centro de Trabajo que se usa para
    filtrar tanto las categorias de averia de la hoja de trabajo
    (mrp.averia.categoria) como el catalogo de Razones de perdida
    (mrp.workcenter.productivity.loss).

    Confirmado en vivo con Laura (24/09): todos los Centros de Trabajo
    ya tienen etiquetas nativas en el campo `tag_ids` de `mrp.workcenter`.
    Por eso este campo NO es de seleccion manual: se calcula solo,
    buscando una etiqueta cuyo nombre contenga el "Texto en la
    etiqueta" de cada tipo.

    1.7.0: los tipos salen del catalogo editable mrp.workcenter.tipo
    (antes, lista fija de 4 en el codigo).
    """
    _inherit = 'mrp.workcenter'

    tipo_centro_trabajo = fields.Selection(
        selection=opciones_tipo_ct,
        string="Tipo de Centro de Trabajo",
        compute='_compute_tipo_centro_trabajo',
        store=True,
        help="Calculado automáticamente a partir de las etiquetas "
             "(tag_ids) del Centro de Trabajo y del catálogo Tipos de "
             "Centro de Trabajo. Determina qué categorías de avería y qué "
             "razones de pérdida se muestran para las órdenes de este "
             "Centro de Trabajo. Un Centro de Trabajo sin ninguna etiqueta "
             "reconocida queda sin tipo y solo ve las categorías/razones "
             "que aplican a todos los tipos.")

    def _tipo_desde_etiquetas(self):
        self.ensure_one()
        nombres = [(tag.name or '').lower() for tag in self.tag_ids]
        for tipo in self.env['mrp.workcenter.tipo'].sudo().with_context(active_test=True).search([]):
            texto = (tipo.texto_etiqueta or '').lower()
            if texto and any(texto in nombre for nombre in nombres):
                return tipo.codigo
        return False

    @api.depends('tag_ids.name')
    def _compute_tipo_centro_trabajo(self):
        for workcenter in self:
            workcenter.tipo_centro_trabajo = workcenter._tipo_desde_etiquetas()
