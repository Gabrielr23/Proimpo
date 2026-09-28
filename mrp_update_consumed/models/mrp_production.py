# -*- coding: utf-8 -*-
"""Cantidad hecha de componentes calculada desde lo realmente transferido.

Reescritura para Odoo 19. Reglas de negocio (validadas en Odoo 18, v0.5/v0.6):

    Cantidad hecha = transferido a pre-producción
                     - devuelto desde pre-producción
                     - desechado desde las órdenes del grupo
                     - ya consumido por órdenes anteriores del grupo (backorders)

  * Es una cantidad física absoluta: NO se escala por qty_producing/product_qty.
  * Solo se calcula si la última transferencia recibida del componente tiene
    "Transferido totalmente" marcado; si no, Cantidad hecha = 0.
  * El consumo ya registrado se descuenta UNA sola vez (solo movimientos de
    consumo hechos de las órdenes del mismo grupo). Así, en un backorder de
    producción solo aparece lo transferido que todavía no se ha consumido.

Mecanismos nativos de Odoo 19 en los que se apoya (verificados en el fuente
de la rama 19.0):
  * Vínculo orden <-> transferencias: stock.move.production_group_id (es el
    mismo que usa mrp.production._compute_picking_ids). Los backorders de una
    orden comparten grupo; las devoluciones copian el campo del movimiento
    original.
  * Dirección (entra / sale de pre-producción): ubicación de origen del propio
    movimiento de componente (move.location_id), no flags. No se usa
    `to_refund`: en Odoo 19 vale True por defecto en todo movimiento nuevo.
  * Desecho: raw_material_production_id + location_dest_id.usage='inventory'
    (el mismo criterio con el que Odoo 19 excluye desechos de move_raw_ids).
  * Consumo: raw_material_production_id + location_dest_id.usage='production'.
  * La cantidad se escribe con el contexto nativo `force_manual_consumption`
    y se marca como consumida (picked), igual que cuando el usuario la edita a
    mano. Así Odoo consume exactamente esa cantidad al producir y su propio
    _set_qty_producing no la vuelve a sobrescribir con la proporción de la LdM.
"""

from markupsafe import Markup, escape

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_round

# Contexto para no recalcular mientras Odoo está cerrando una orden
# (button_mark_done divide movimientos, crea backorders, etc.).
MUC_SKIP = 'muc_skip_recompute'

OPEN_STATES = ('confirmed', 'progress', 'to_close')


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # ------------------------------------------------------------------
    # Disparadores
    # ------------------------------------------------------------------

    def _set_qty_producing(self, pick_manual_consumption_moves=True):
        """Odoo 19 llama a este método cada vez que cambia la cantidad a
        producir: onchange del formulario, asistente "Cambiar cantidad a
        producir", órdenes de trabajo, números de serie... Recalcular aquí,
        después de super(), garantiza que la Cantidad hecha final sea la
        nuestra y no la proporción de la LdM, sin reemplazar el onchange
        nativo."""
        res = super()._set_qty_producing(pick_manual_consumption_moves)
        if not self.env.context.get(MUC_SKIP):
            self._muc_recompute()
        return res

    @api.onchange('product_qty')
    def _muc_onchange_product_qty(self):
        self._muc_recompute()

    def write(self, vals):
        res = super().write(vals)
        if ('product_qty' in vals or 'qty_producing' in vals) \
                and not self.env.context.get(MUC_SKIP):
            self._muc_recompute()
        return res

    def button_mark_done(self):
        for production in self:
            # Las órdenes de subcontratación las cierra Odoo desde la recepción.
            if 'subcontractor_id' in production._fields and production.subcontractor_id:
                continue
            if production.product_uom_id.is_zero(production.qty_producing):
                raise ValidationError(_("Debe poner un valor mayor a 0 en cantidad."))
        res = super(MrpProduction, self.with_context(**{MUC_SKIP: True})).button_mark_done()
        # Backorder(s) creados al producir: mostrar solo lo pendiente.
        self._muc_open_productions(self.production_group_id)._muc_recompute()
        return res

    def action_recompute_consumed_quantities(self):
        """Botón "Recalcular consumo" y acción de servidor de la lista.
        Además de recalcular, deja el detalle del cálculo en el chatter."""
        for production in self:
            diag = []
            production._muc_recompute(diag=diag)
            if diag:
                body = Markup("<b>Recalcular consumo — detalle:</b><br/>") + \
                    Markup("<br/>").join(escape(line) for line in diag)
                production.message_post(body=body)
        return True

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------

    @api.model
    def _muc_open_productions(self, groups):
        return groups.production_ids.filtered(lambda p: p.state in OPEN_STATES)

    def _muc_recompute(self, diag=None):
        for production in self:
            if production.state not in OPEN_STATES:
                continue
            in_onchange = not isinstance(production.id, int)
            seen_products = set()
            for move in production.move_raw_ids:
                if move.state in ('done', 'cancel') or not move.product_id:
                    continue
                if move.product_id.id in seen_products:
                    # Mismo componente en dos líneas: el total va en la primera.
                    qty, line = 0.0, "• %s: línea repetida del mismo componente → 0 " \
                                     "(el total quedó en la primera línea)" % move.product_id.display_name
                else:
                    seen_products.add(move.product_id.id)
                    qty, line = production._muc_compute_qty(move)
                if diag is not None:
                    diag.append(line)
                production._muc_apply(move, qty, in_onchange)

    def _muc_compute_qty(self, raw_move):
        """Devuelve (cantidad, línea de diagnóstico) para un componente, en la
        unidad de medida del movimiento de componente."""
        self.ensure_one()
        product = raw_move.product_id
        uom = raw_move.product_uom
        name = product.display_name
        anchor = raw_move.location_id  # ubicación de componentes (pre-producción)
        group = self.production_group_id
        if not anchor or not group:
            return 0.0, "• %s: la orden no tiene grupo de producción o ubicación de " \
                        "componentes → 0" % name

        Move = self.env['stock.move']
        group_production_ids = group.production_ids.ids
        base = [('product_id', '=', product.id), ('state', '=', 'done')]

        transfer_moves = Move.search(base + [
            ('production_group_id', '=', group.id),
            ('picking_id', '!=', False),
            '|',
            ('picking_type_id.consumed', '=', True),
            ('origin_returned_move_id.picking_type_id.consumed', '=', True),
        ], order='date desc, id desc')
        incoming = transfer_moves.filtered(
            lambda m: m.location_dest_id._child_of(anchor) and not m.location_id._child_of(anchor))
        returned = transfer_moves.filtered(
            lambda m: m.location_id._child_of(anchor)
            and not m.location_dest_id._child_of(anchor)
            and m.location_dest_id.usage in ('internal', 'transit'))

        # Regla "Transferido totalmente": manda la última transferencia recibida.
        last_incoming = incoming[:1]
        if not last_incoming or not last_incoming.picking_id.totally_transferred:
            return 0.0, "• %s: sin Pick Components hecho con 'Transferido totalmente' " \
                        "marcado → Cantidad hecha = 0 (última transferencia: %s)" % (
                            name, last_incoming.picking_id.display_name or '(ninguna)')

        scrapped = Move.search(base + [
            ('raw_material_production_id', 'in', group_production_ids),
            ('location_dest_id.usage', '=', 'inventory'),
        ]).filtered(lambda m: m.location_id._child_of(anchor))
        consumed = Move.search(base + [
            ('raw_material_production_id', 'in', group_production_ids),
            ('location_dest_id.usage', '=', 'production'),
        ]).filtered(lambda m: m.location_id._child_of(anchor))

        def total(moves):
            return sum(m.product_uom._compute_quantity(m.quantity, uom, round=False) for m in moves)

        qty_in, qty_ret = total(incoming), total(returned)
        qty_scrap, qty_consumed = total(scrapped), total(consumed)
        qty = self._muc_round(max(qty_in - qty_ret - qty_scrap - qty_consumed, 0.0), uom)
        line = "• %s: transferido %.2f − devuelto %.2f − desechado %.2f − ya consumido " \
               "%.2f = %.2f %s (antes: %.2f)" % (
                   name, qty_in, qty_ret, qty_scrap, qty_consumed, qty, uom.name, raw_move.quantity)
        return qty, line

    def _muc_round(self, qty, uom):
        # _set_quantity de stock.move rechaza cantidades con más decimales que
        # la precisión 'Product Unit'; se redondea a la UdM y a esa precisión.
        digits = self.env['decimal.precision'].precision_get('Product Unit')
        return float_round(uom.round(qty), precision_digits=digits, rounding_method='HALF-UP')

    def _muc_apply(self, move, qty, in_onchange=False):
        if in_onchange:
            # Vista previa en el formulario (registro aún no guardado).
            move.quantity = qty
            move.manual_consumption = True
            move.picked = bool(qty)
            return
        if move.product_uom.compare(move.quantity, qty) != 0:
            move.with_context(force_manual_consumption=True).write({'quantity': qty})
        extra = {}
        if not move.manual_consumption:
            extra['manual_consumption'] = True
        if qty and not move.picked:
            extra['picked'] = True
        if extra:
            move.write(extra)
