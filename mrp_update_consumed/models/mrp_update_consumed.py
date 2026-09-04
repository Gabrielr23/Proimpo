# -*- coding: utf-8 -*-

import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    _description = 'Actualiza los valores consumidos desde los picking de transferencia'

    # ------------------------------------------------------------------
    # NOTA DE LA CORRECCIÓN (Desecho / Devolución no se restaban bien)
    # ------------------------------------------------------------------
    # La versión anterior clasificaba cada stock.move como "suma" o "resta"
    # usando dos señales indirectas: picking_type_id.code y to_refund.
    # Eso rompía con dos procesos reales de esta base:
    #
    #   1. Desecho (stock.scrap): el move que genera un scrap NUNCA trae
    #      picking_type_id ni group_id (así lo crea Odoo en
    #      addons/stock/models/stock_scrap.py y en la extensión de mrp,
    #      addons/mrp/models/stock_scrap.py). Como el query original
    #      filtraba por ambos campos, el move de scrap era invisible para
    #      el cálculo, sin importar cómo se ajustaran las ramas del
    #      if/elif: nunca llegaba a evaluarse.
    #
    #   2. Devolución (botón "Devolver"): en esta base, la devolución de un
    #      Pick Components reutiliza el MISMO picking_type_id ("PROIMPO:
    #      Pick Components", code='internal', consumed=True) que el PC
    #      original, solo que en sentido contrario (Pre-Production -> WH/
    #      Stock en vez de WH/Stock -> Pre-Production). El campo to_refund
    #      es un flag de facturación/costeo que el usuario marca a mano en
    #      el asistente de devolución, no algo que Odoo active
    #      automáticamente para señalar "esto es una devolución". Si no se
    #      marcó, to_refund queda en False y la devolución caía en la misma
    #      rama que un PC normal: se SUMABA en vez de restarse.
    #
    # La corrección reemplaza esas dos señales por datos que Odoo sí
    # garantiza de forma consistente:
    #   - Para los moves de tipo 'internal' (PC / Devolución): la dirección
    #     real del movimiento (location_id -> location_dest_id) comparada
    #     contra las ubicaciones por defecto del propio tipo de operación.
    #   - Para el Desecho: raw_material_production_id (el campo que Odoo sí
    #     setea siempre en el move de scrap de un componente) + scrapped.
    # ------------------------------------------------------------------

    @api.onchange('qty_producing')
    def _onchange_qty_producing(self):
        for move_line in self.move_raw_ids:
            self._update_move_raw_quantity(move_line)

    def _update_move_raw_quantity(self, move_line):
        """Recalcula move_line.quantity ("Cantidad hecha") para un
        componente de esta MO, sumando los Pick Components transferidos y
        restando Devoluciones, Desechos y el consumo ya registrado en la
        propia MO."""
        self.ensure_one()
        move_line.ensure_one()

        product_id = move_line.product_id.id
        group_id = move_line.group_id.id
        if not product_id:
            return

        last_pc_move = self.env['stock.move'].search([
            ('product_id', '=', product_id),
            ('group_id', '=', group_id),
            ('state', '=', 'done'),
            ('picking_type_id.code', '=', 'internal'),
            ('picking_type_id.consumed', '=', True),
            ('to_refund', '=', False),
        ], order="date desc", limit=1)

        if not last_pc_move.picking_id.totally_transferred:
            return

        move_stock_all = self.env['stock.move'].search([
            ('product_id', '=', product_id),
            ('picking_type_id.consumed', '=', True),
            ('group_id', '=', group_id),
            ('state', '=', 'done'),
        ])

        qty_all = 0.0
        for move_all in move_stock_all:
            picking_type = move_all.picking_type_id
            if picking_type.code == 'internal':
                qty_all += self._get_internal_move_signed_qty(move_all, picking_type)
            elif picking_type.code == 'mrp_operation':
                qty_all -= move_all.quantity
            elif move_all.to_refund:
                # Compatibilidad con otros tipos de operación (distintos de
                # 'internal') marcados manualmente como to_refund.
                qty_all -= move_all.quantity

        qty_all -= self._get_scrapped_qty(product_id)

        qty_consumed = self.move_stock_no_done(product_id, group_id) or 0.0

        if not self.product_qty:
            return

        new_quantity = round(
            ((qty_all - qty_consumed) / self.product_qty) * self.qty_producing, 2
        )
        if new_quantity != move_line.quantity:
            move_line.quantity = new_quantity

    def _get_internal_move_signed_qty(self, move, picking_type=None):
        """Cantidad de `move` con signo, para moves de tipo 'internal'.

        Se determina por la dirección real del movimiento respecto de las
        ubicaciones por defecto del tipo de operación:
          - origen -> destino "normal" del tipo de operación (p.ej. WH/Stock
            -> Pre-Production): PC normal o reposición -> suma.
          - destino -> origen "normal" (p.ej. Pre-Production -> WH/Stock):
            Devolución -> resta.
        Si to_refund viene marcado explícitamente, se respeta y se resta,
        sin importar la dirección (permite marcar a mano un caso especial).
        Si no se puede determinar la dirección (el tipo de operación no
        tiene ubicaciones por defecto configuradas), no se suma ni resta y
        se deja un log para revisión manual, en vez de arriesgar el signo.
        """
        picking_type = picking_type or move.picking_type_id

        if move.to_refund:
            return -move.quantity

        src = picking_type.default_location_src_id
        dest = picking_type.default_location_dest_id

        if src and dest and move.location_id.id == src.id and move.location_dest_id.id == dest.id:
            return move.quantity
        if src and dest and move.location_id.id == dest.id and move.location_dest_id.id == src.id:
            return -move.quantity

        _logger.warning(
            "mrp_update_consumed: no se pudo determinar la dirección del movimiento "
            "%s (%s -> %s) para el tipo de operación '%s' (revisar que tenga "
            "configuradas sus ubicaciones origen/destino por defecto). No se sumó "
            "ni restó en el cálculo de cantidad consumida.",
            move.id, move.location_id.display_name, move.location_dest_id.display_name,
            picking_type.display_name,
        )
        return 0.0

    def _get_scrapped_qty(self, product_id):
        """Cantidad desechada (Desecho/Scrap) de `product_id` para esta MO.

        El move que genera un stock.scrap nunca trae picking_type_id ni
        group_id, así que no se puede detectar con el mismo dominio que el
        resto de movimientos: se vincula por raw_material_production_id,
        que es el campo que Odoo sí setea siempre para el scrap de un
        componente de fabricación."""
        self.ensure_one()
        scrap_moves = self.env['stock.move'].search([
            ('raw_material_production_id', '=', self.id),
            ('product_id', '=', product_id),
            ('state', '=', 'done'),
            ('scrapped', '=', True),
        ])
        return sum(scrap_moves.mapped('quantity'))

    def button_mark_done(self):
        if self.qty_producing == 0:
            raise ValidationError(_("Debe poner un valor mayor a 0 en cantidad."))
        return super(MrpProduction, self).button_mark_done()

    def move_stock_no_done(self, product_id, group_id):
        move_stock = self.env['stock.move'].search([
            ('product_id', '=', product_id),
            ('group_id', '=', group_id),
            ('state', '=', 'done'),
            ('picking_type_id.code', '=', 'mrp_operation'),
            ('to_refund', '=', False),
        ])
        return sum(move_stock.mapped('quantity'))

    def action_recompute_consumed_quantities(self):
        """Recalcula 'Cantidad hecha' de los componentes con la lógica
        corregida. Pensado para corregir órdenes ya afectadas por el bug de
        Desecho/Devolución (por ejemplo WH/MO/45940 y WH/MO/45939).

        Se puede ejecutar seleccionando una o varias Órdenes de fabricación
        en la vista de lista y usando la acción "Recalcular cantidad
        consumida (Desecho/Devolución)"."""
        for production in self:
            for move_line in production.move_raw_ids:
                production._update_move_raw_quantity(move_line)
        return True


class MrpProductionWorkcenterLine(models.Model):
    _inherit = "mrp.workorder"

    progress = fields.Float(string="Progreso (%)", compute='_progress_time', digits=(3, 2))

    @api.depends('duration')
    def _progress_time(self):
        for line in self:
            if line.duration > 0.0 and line.duration_expected > 0.0:
                line.progress = (line.duration / line.duration_expected) * 100
            else:
                line.progress = 0.0
