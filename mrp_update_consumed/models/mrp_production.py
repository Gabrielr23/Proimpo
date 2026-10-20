# -*- coding: utf-8 -*-
"""Cantidad hecha de los componentes a partir de lo realmente transferido
(Odoo 19) — 19.0.1.3.0.

Mismas reglas que la v0.8 de Odoo 18, ya probada en test y producción:

Disponible de un componente para el grupo de la orden (orden + backorders)
    = Pick Components enviados (a Pre-Production O a un taller externo; no
      importa el destino, como el módulo original)
    - devoluciones (se reconocen por el destino, nunca por `to_refund`, que
      en Odoo 19 vale True por defecto en todo movimiento)
    - desechos de todas las órdenes del grupo
    - lo ya consumido por órdenes anteriores del grupo (una sola vez)
  Un Pick Components que solo mueve material dentro de la zona de producción
  (taller -> Pre-Production) no se suma dos veces.

Cantidad hecha:
  * Cierre parcial (queda backorder): proporción de la lista de materiales de
    la cantidad a producir (lo nativo), con tope en lo disponible.
  * Cierre final (todo lo pendiente, "Sin backorder" o tipo de operación sin
    backorder): TODO lo disponible.
  * Nunca negativo.
  * Condición: la última transferencia enviada del componente debe tener
    "Transferido totalmente". Si no la hay, el módulo no interviene: el
    componente queda con la proporción nativa de la LdM y Odoo valida el
    inventario al cerrar (19.0.1.2.0).

Valor manual del operario (19.0.1.3.0, igual que la v0.10.1 de Odoo 18):
  * Con transferencia: gana siempre lo transferido (aunque ponga 0).
  * Sin transferencia: se conserva lo que digitó; con 0 no se consume y con
    un valor mayor Odoo valida el inventario al cerrar (nativo).

Diferencias de Odoo 19 tenidas en cuenta (errores vistos en la migración):
  * Vínculo orden <-> transferencias: `production_group_id` (ya no existe
    `group_id` / procurement.group).
  * Desecho: destino con `usage = 'inventory'` (ya no existen `scrapped` ni
    `scrap_location`).
  * No se sobrescribe el onchange nativo `_onchange_qty_producing` (mismo
    nombre en 19): el recálculo se engancha después de `_set_qty_producing`.
  * `button_mark_done` valida la cantidad por orden: `mrp_subcontracting` lo
    llama con un recordset vacío al validar cualquier transferencia.
  * Precisión decimal 'Product Unit'; sin imports de `decimal_precision`.
"""

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_round

# Evita recalcular mientras Odoo cierra la orden (divide movimientos, crea
# backorders): el valor ya quedó fijado justo antes de cerrar.
MUC_SKIP = 'muc_skip_recompute'
# Escrituras del propio módulo (no son ajustes manuales del operario).
MUC_WRITING = 'muc_writing'
OPEN_STATES = ('confirmed', 'progress', 'to_close')


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # ------------------------------------------------------------------
    # Disparadores
    # ------------------------------------------------------------------

    def _set_qty_producing(self, pick_manual_consumption_moves=True):
        """Odoo 19 llama a este método cada vez que cambia la cantidad a
        producir (formulario, asistente "Cambiar cantidad", órdenes de
        trabajo). Recalcular después de super() deja el valor del módulo sin
        reemplazar el onchange nativo."""
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
        if not self.env.context.get(MUC_SKIP):
            # Fijar la Cantidad hecha justo antes de cerrar: parcial o final
            # según el caso (incluye "Sin backorder").
            for production in self:
                production._muc_recompute(final=production._muc_is_final_close())
        res = super(MrpProduction, self.with_context(**{MUC_SKIP: True})).button_mark_done()
        # Si Odoo abre un asistente (backorder / consumo), su contexto no debe
        # arrastrar la marca: al confirmarlo se recalcula (p. ej. "Sin backorder").
        if isinstance(res, dict) and isinstance(res.get('context'), dict):
            res['context'] = {k: v for k, v in res['context'].items() if k != MUC_SKIP}
        # Backorders que quedaron abiertos: recalcular con lo pendiente.
        self._muc_open_productions(self.production_group_id)._muc_recompute()
        return res

    def action_recompute_consumed_quantities(self):
        """Botón "Recalcular consumo" / acción de la lista: recalcula y deja
        el detalle del cálculo en el chatter."""
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

    def _muc_is_final_close(self):
        """¿Este cierre termina la orden (no quedará backorder)?"""
        self.ensure_one()
        ctx = self.env.context
        if ctx.get('skip_backorder') and self.id not in (ctx.get('mo_ids_to_backorder') or []):
            return True  # eligieron "Sin backorder"
        if self.picking_type_id.create_backorder == 'never':
            return True
        pending = self.product_qty - self.qty_produced
        return self.product_uom_id.compare(self.qty_producing, pending) >= 0

    def _muc_plan(self, final=None, diag=None, ignore_manual=None):
        """Lo que el módulo pondría en cada componente abierto, sin escribir.
        Devuelve [(movimiento, cantidad, tipo)] con tipo:
          'module' -> calculado desde lo transferido (gana sobre lo manual)
          'native' -> sin transferencia: proporción LdM (nativo)
          'manual' -> sin transferencia, valor digitado por el operario
        `ignore_manual`: movimientos cuya marca manual no se tiene en cuenta
        (para saber qué habría puesto el módulo)."""
        self.ensure_one()
        ignore_manual = ignore_manual or self.env['stock.move']
        is_final = self._muc_is_final_close() if final is None else final
        plan = []
        available_by_product = {}
        for move in self.move_raw_ids:
            if move.state in ('done', 'cancel') or not move.product_id:
                continue
            key = move.product_id.id
            if key not in available_by_product:
                available_by_product[key] = self._muc_available(move, diag)
            available = available_by_product[key]
            manual = move.muc_manual and move not in ignore_manual
            name = move.product_id.display_name
            if available is None:
                if manual:
                    # Sin transferencia y valor del operario (también 0): se
                    # respeta; si es mayor que 0, Odoo valida el inventario.
                    if diag is not None:
                        diag.append("   → %s: sin transferencia, valor manual del operario "
                                    "= %.2f %s (se conserva)" % (name, move.quantity, move.product_uom.name))
                    plan.append((move, move.quantity, 'manual'))
                    continue
                # Sin Pick Components con "Transferido totalmente": como lo pone
                # Odoo (proporción de la LdM); al cerrar, Odoo valida el
                # inventario como siempre.
                native = self._muc_round(max(
                    (self.qty_producing - self.qty_produced) * move.unit_factor, 0.0), move.product_uom)
                if diag is not None:
                    diag.append("   → %s: sin transferencia → comportamiento nativo de Odoo "
                                "(proporción LdM) = %.2f %s" % (name, native, move.product_uom.name))
                plan.append((move, native, 'native'))
                continue
            # Con transferencia, cualquier valor manual (también 0) lo
            # reemplaza lo transferido: gana la transferencia.
            if is_final:
                qty = available
            else:
                native = (self.qty_producing - self.qty_produced) * move.unit_factor
                qty = min(max(native, 0.0), available)
            qty = self._muc_round(max(qty, 0.0), move.product_uom)
            available_by_product[key] = max(available - qty, 0.0)
            if diag is not None:
                diag.append("   → %s: %s → Cantidad hecha = %.2f %s (antes: %.2f%s)" % (
                    name,
                    "cierre final (todo lo disponible)" if is_final else "cierre parcial (proporción LdM)",
                    qty, move.product_uom.name, move.quantity,
                    ", manual del operario: gana la transferencia" if manual else ""))
            plan.append((move, qty, 'module'))
        return plan

    def _muc_recompute(self, final=None, diag=None):
        for production in self:
            if production.state not in OPEN_STATES:
                continue
            for move, qty, kind in production._muc_plan(final=final, diag=diag):
                if kind == 'manual':
                    continue
                if kind == 'native':
                    production._muc_apply_native(move, qty)
                else:
                    production._muc_apply(move, qty)

    def _muc_register_manual(self, moves):
        """El operario cambió la Cantidad hecha de `moves`: sin transferencia,
        marcar como manual lo que no coincide con la proporción nativa."""
        self.ensure_one()
        expected = {m.id: (q, kind) for m, q, kind in self._muc_plan(ignore_manual=moves)}
        for move in moves:
            if move.id not in expected:
                continue
            qty, kind = expected[move.id]
            # Con transferencia gana siempre lo transferido.
            manual = kind != 'module' and bool(move.product_uom.compare(move.quantity, qty))
            vals = {}
            if manual != move.muc_manual:
                vals['muc_manual'] = manual
            if manual:
                # Igual que Odoo cuando el usuario digita: consumo manual.
                if not move.manual_consumption:
                    vals['manual_consumption'] = True
                if not move.picked:
                    vals['picked'] = True
            if vals:
                move.with_context(**{MUC_WRITING: True}).write(vals)

    def _muc_available(self, raw_move, diag=None):
        """Disponible del componente para el grupo, en la UdM del movimiento
        de componente. None si no se cumple "Transferido totalmente"."""
        self.ensure_one()
        product = raw_move.product_id
        uom = raw_move.product_uom
        name = product.display_name
        group = self.production_group_id
        if not group:
            if diag is not None:
                diag.append("• %s: la orden no tiene grupo de producción → 0" % name)
            return None
        Move = self.env['stock.move']

        def qty(move):
            return move.product_uom._compute_quantity(move.quantity, uom, round=False)

        transfers = Move.search([
            ('product_id', '=', product.id),
            ('production_group_id', '=', group.id),
            ('state', '=', 'done'),
            ('picking_id', '!=', False),
            '|',
            ('picking_type_id.consumed', '=', True),
            ('origin_returned_move_id.picking_type_id.consumed', '=', True),
        ], order='date asc, id asc')

        # Zona de producción = ubicación de componentes de la orden + todo
        # destino de un Pick Components (Pre-Production o taller). Nunca la
        # ubicación de origen del Pick Components (WH/Stock).
        sources = transfers.picking_type_id.default_location_src_id
        zone = raw_move.location_id | self.location_src_id
        for t in transfers:
            if not t.origin_returned_move_id and t.location_dest_id not in sources:
                zone |= t.location_dest_id

        def in_zone(loc):
            return any(loc._child_of(z) for z in zone)

        sent = returned = 0.0
        last_sent = Move
        for t in transfers:
            src_in, dst_in = in_zone(t.location_id), in_zone(t.location_dest_id)
            if dst_in and not src_in:
                sent += qty(t)
                last_sent = t
            elif src_in and not dst_in:
                returned += qty(t)
            # dentro de la zona (taller -> Pre-Production): no cambia el total

        if not last_sent or not last_sent.picking_id.totally_transferred:
            if diag is not None:
                diag.append("• %s: sin Pick Components hecho con 'Transferido totalmente' "
                            "marcado → Cantidad hecha = 0 (último enviado: %s)" % (
                                name, last_sent.picking_id.display_name or '(ninguno)'))
            return None

        group_mo_domain = [
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('raw_material_production_id', 'in', group.production_ids.ids),
        ]
        scrapped = sum(qty(m) for m in Move.search(
            group_mo_domain + [('location_dest_id.usage', '=', 'inventory')]))
        consumed = sum(qty(m) for m in Move.search(
            group_mo_domain + [('location_dest_id.usage', '=', 'production')]))
        available = max(sent - returned - scrapped - consumed, 0.0)
        if diag is not None:
            diag.append("• %s: enviado %.2f − devuelto %.2f − desechado %.2f − ya consumido %.2f "
                        "= disponible %.2f %s" % (name, sent, returned, scrapped, consumed,
                                                   available, uom.name))
        return available

    def _muc_round(self, qty, uom):
        # stock.move rechaza cantidades con más decimales que 'Product Unit'.
        digits = self.env['decimal.precision'].precision_get('Product Unit')
        return float_round(uom.round(qty), precision_digits=digits, rounding_method='HALF-UP')

    def _muc_apply_native(self, move, qty):
        """Deja el componente como lo hace Odoo de forma nativa: cantidad
        proporcional, sin consumo manual (así Odoo la sigue ajustando y valida
        el inventario al cerrar)."""
        if not isinstance(move.id, int):  # vista previa en el formulario
            if move.product_uom.compare(move.quantity, qty):
                move.quantity = qty
            move.manual_consumption = False
            move.picked = bool(qty)
            return
        move = move.with_context(**{MUC_WRITING: True})
        if move.product_uom.compare(move.quantity, qty):
            move.write({'quantity': qty})
        extra = {}
        if move.muc_manual:
            extra['muc_manual'] = False
        if move.manual_consumption:
            extra['manual_consumption'] = False
        if bool(qty) != move.picked:
            extra['picked'] = bool(qty)
        if extra:
            move.write(extra)

    def _muc_apply(self, move, qty):
        if not isinstance(move.id, int):  # vista previa en el formulario
            if move.product_uom.compare(move.quantity, qty):
                move.quantity = qty
                move.manual_consumption = True
                move.picked = bool(qty)
            return
        move = move.with_context(**{MUC_WRITING: True})
        if move.product_uom.compare(move.quantity, qty):
            move.with_context(force_manual_consumption=True).write({'quantity': qty})
        # Igual que cuando el usuario digita la cantidad: Odoo consume
        # exactamente esto al producir y no lo cambia por la proporción LdM.
        extra = {}
        if move.muc_manual:
            extra['muc_manual'] = False
        if not move.manual_consumption:
            extra['manual_consumption'] = True
        if qty:
            extra['picked'] = True
        if extra:
            move.write(extra)


class StockMove(models.Model):
    _inherit = 'stock.move'

    muc_manual = fields.Boolean(
        string="Cantidad hecha manual", copy=False,
        help="El operario digitó la Cantidad hecha de este componente sin "
             "transferencia: se conserva su valor (también 0). Con "
             "transferencia gana siempre lo transferido.")

    def write(self, vals):
        ctx = self.env.context
        # En Odoo 19 la proporción nativa escribe move_line_ids sin marca de
        # contexto, por eso solo se toma como manual el cambio de 'quantity'.
        track = 'quantity' in vals and not ctx.get(MUC_WRITING) and not ctx.get(MUC_SKIP)
        res = super().write(vals)
        if track:
            moves = self.filtered(lambda m: m.raw_material_production_id
                                  and m.state not in ('done', 'cancel')
                                  and m.raw_material_production_id.state in OPEN_STATES)
            for production in moves.raw_material_production_id:
                production._muc_register_manual(moves & production.move_raw_ids)
                production._muc_recompute()
        return res
