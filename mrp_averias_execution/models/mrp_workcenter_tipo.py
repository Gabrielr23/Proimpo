# -*- coding: utf-8 -*-
import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.sql import table_exists

# Los 4 tipos con los que nació el módulo. Se usan como respaldo si la
# tabla del catálogo todavía no existe (primer arranque al actualizar).
TIPOS_INICIALES = [
    ('inyectoras', "Inyectoras"),
    ('sopladoras', "Sopladoras"),
    ('impresion', "Impresión"),
    ('sellado', "Sellado"),
]


def opciones_tipo_ct(model):
    """Opciones del campo "Tipo de Centro de Trabajo" en todos los
    modelos que lo usan (centro de trabajo, razones de pérdida,
    categorías de avería, reporte, wizard). Salen del catálogo
    mrp.workcenter.tipo, así que un tipo nuevo no requiere código.
    El valor guardado es el código del tipo: los valores de antes
    (inyectoras, sopladoras, impresion, sellado) siguen siendo válidos.
    """
    return model.env['mrp.workcenter.tipo']._opciones()


def _codigo_desde_nombre(nombre):
    texto = unicodedata.normalize('NFKD', nombre or '')
    texto = texto.encode('ascii', 'ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]+', '_', texto).strip('_')


class MrpWorkcenterTipo(models.Model):
    """Catálogo editable de tipos de Centro de Trabajo (1.7.0).

    Antes era una lista fija en el código. El tipo de cada CT se sigue
    calculando solo desde sus etiquetas: el primer tipo (por secuencia)
    cuyo "Texto en la etiqueta" aparezca en el nombre de alguna
    etiqueta del CT.
    """
    _name = 'mrp.workcenter.tipo'
    _description = "Tipo de Centro de Trabajo"
    _order = 'sequence, id'

    name = fields.Char(string="Nombre", required=True)
    codigo = fields.Char(
        string="Código", copy=False,
        help="Valor interno que se guarda en los registros. Se genera "
             "solo desde el nombre y no se puede cambiar después.")
    texto_etiqueta = fields.Char(
        string="Texto en la etiqueta", required=True,
        help="Texto que se busca (sin distinguir mayúsculas) en el nombre "
             "de las etiquetas del Centro de Trabajo. Ej.: 'inyector' "
             "reconoce las etiquetas 'Inyectoras' e 'Inyector'.")
    sequence = fields.Integer(string="Secuencia", default=10)
    active = fields.Boolean(default=True)
    workcenter_count = fields.Integer(
        string="Centros de trabajo", compute='_compute_workcenter_count')

    _sql_constraints = [
        ('codigo_unico', 'unique(codigo)',
         "Ya existe un tipo de Centro de Trabajo con ese código."),
    ]

    @api.model
    def _opciones(self):
        if not table_exists(self.env.cr, self._table):
            return list(TIPOS_INICIALES)
        tipos = self.sudo().with_context(active_test=False).search([])
        opciones = [(t.codigo, t.name) for t in tipos if t.codigo]
        return opciones or list(TIPOS_INICIALES)

    def _compute_workcenter_count(self):
        Wc = self.env['mrp.workcenter']
        for tipo in self:
            tipo.workcenter_count = Wc.search_count(
                [('tipo_centro_trabajo', '=', tipo.codigo)]) if tipo.codigo else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('codigo'):
                vals['codigo'] = _codigo_desde_nombre(vals.get('name'))
            if not vals['codigo']:
                raise UserError(_("El nombre del tipo debe tener letras o números."))
            vals['texto_etiqueta'] = (vals.get('texto_etiqueta') or '').strip().lower()
        tipos = super().create(vals_list)
        self._recalcular_centros()
        return tipos

    def write(self, vals):
        if 'codigo' in vals and any(t.codigo and t.codigo != vals['codigo'] for t in self):
            raise UserError(_(
                "El código de un tipo no se puede cambiar: está guardado en "
                "centros de trabajo, razones de pérdida y averías. Cambia el "
                "nombre, o crea un tipo nuevo y archiva este."))
        if 'texto_etiqueta' in vals:
            vals['texto_etiqueta'] = (vals['texto_etiqueta'] or '').strip().lower()
        res = super().write(vals)
        if {'texto_etiqueta', 'sequence', 'active'} & set(vals):
            self._recalcular_centros()
        return res

    def unlink(self):
        for tipo in self:
            usado = (
                self.env['mrp.workcenter'].search_count([('tipo_centro_trabajo', '=', tipo.codigo)])
                or self.env['mrp.workcenter.productivity.loss'].with_context(active_test=False).search_count(
                    [('tipo_centro_trabajo', '=', tipo.codigo)])
                or self.env['mrp.averia.categoria'].with_context(active_test=False).search_count(
                    [('tipo_centro_trabajo', '=', tipo.codigo)]))
            if usado:
                raise UserError(_(
                    "El tipo \"%(tipo)s\" está en uso (centros de trabajo, "
                    "razones de pérdida o categorías de avería). Archívalo en "
                    "vez de borrarlo.", tipo=tipo.name))
        return super().unlink()

    @api.model
    def _recalcular_centros(self):
        """Vuelve a calcular el tipo de todos los centros de trabajo y
        escribe solo los que cambian (así el tipo guardado en el
        Seguimiento de tiempo se actualiza solo en esos CT)."""
        Wc = self.env['mrp.workcenter'].sudo().with_context(active_test=False)
        for wc in Wc.search([]):
            nuevo = wc._tipo_desde_etiquetas()
            if nuevo != wc.tipo_centro_trabajo:
                wc.write({'tipo_centro_trabajo': nuevo})
