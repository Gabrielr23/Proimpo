# -*- coding: utf-8 -*-
"""Cantidad hecha de los componentes a partir de lo realmente transferido
(Odoo 18) — v0.8.

Base: el comportamiento del módulo original (el que funcionaba en planta),
más los arreglos y acuerdos con PROIMPO:

Disponible de un componente para el grupo de la orden (orden + backorders)
    = Pick Components enviados (a Pre-Production O a un taller externo; como
      el original, no importa el destino)
    - devoluciones de esos Pick Components (se reconocen por el destino, no
      por la casilla "Actualizar cantidades en OV/OC")
    - desechos de todas las órdenes del grupo
    - lo ya consumido por órdenes anteriores del grupo (una sola vez)
  Un Pick Components que solo mueve material que ya estaba en la zona de
  producción (p. ej. taller -> Pre-Production) no se suma dos veces.

Cantidad hecha:
  * Cierre parcial (queda backorder): proporción de la lista de materiales de
    la cantidad a producir (lo que Odoo pone de forma nativa), con tope en lo
    disponible.
  * Cierre final (se produce todo lo pendiente, o se elige "Sin backorder", o
    el tipo de operación nunca crea backorder): TODO lo disponible. Así se
    liquidan sobreconsumos, traslados adicionales, desechos y devoluciones.
  * Nunca negativo.
  * Condición: la última transferencia enviada del componente debe tener
    "Transferido totalmente"; si no, Cantidad hecha = 0.
"""

from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import html_escape
from odoo.tools.float_utils import float_compare, float_round

# Evita recalcular mientras Odoo cierra la orden (divide movimientos, crea
# backorders): el valor ya quedó fijado justo antes de cerrar.
MUC_SKIP = 'muc_skip_recompute'
OPEN_STATES = ('confirmed', 'progress', 'to_close')


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    _description = 'Actualiza los valores consumidos desde los picking de transferencia'

    # ------------------------------------------------------------------
    # Disparadores
    # ------------------------------------------------------------------

    @api.onchange('qty_producing', 'product_qty')
    def _onchange_qty_producing(self):
        """Vista previa en el formulario (lo definitivo lo hace write)."""
        self._muc_recompute()

    def write(self, vals):
        res = super().write(vals)
        if ('product_qty' in vals or 'qty_producing' in vals) \
                and not self.env.context.get(MUC_SKIP):
            self._muc_recompute()
        return res

    def button_mark_done(self):
        for production in self:
            if production.qty_producing == 0:
                raise ValidationError(_("Debe poner un valor mayor a 0 en cantidad."))
        if not self.env.context.get(MUC_SKIP):
            # Fijar la Cantidad hecha justo antes de cerrar: parcial o final
            # según lo que se esté haciendo (incluye "Sin backorder").
            for production in self:
                production._muc_recompute(final=production._muc_is_final_close())
        res = super(MrpProduction, self.with_context(**{MUC_SKIP: True})).button_mark_done()
        # Si Odoo abre un asistente (backorder / consumo), que su contexto no
        # arrastre la marca: al confirmarlo se debe recalcular de nuevo (p. ej.
        # "Sin backorder" = cierre final).
        if isinstance(res, dict) and isinstance(res.get('context'), dict):
            res['context'] = {k: v for k, v in res['context'].items() if k != MUC_SKIP}
        # Backorders que quedaron abiertos: recalcular con lo pendiente.
        if self.procurement_group_id:
            self.search([
                ('procurement_group_id', 'in', self.procurement_group_id.ids),
                ('state', 'in', OPEN_STATES),
            ])._muc_recompute()
        return res

    def action_recompute_consumed_quantities(self):
        """Botón "Recalcular consumo" / acción de la lista: recalcula y deja
        el detalle del cálculo en el chatter."""
        for production in self:
            diag = []
            production._muc_recompute(diag=diag)
            if diag:
                safe_lines = Markup("<br/>").join(Markup(html_escape(line)) for line in diag)
                production.message_post(
                    body=Markup("<b>Recalcular consumo — detalle:</b><br/>%s") % safe_lines)
        return True

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------

    def _muc_is_final_close(self):
        """¿Este cierre termina la orden (no quedará backorder)?"""
        self.ensure_one()
        ctx = self.env.context
        if ctx.get('skip_backorder') and self.id not in (ctx.get('mo_ids_to_backorder') or []):
            return True  # eligieron "Sin backorder"
        if self.picking_type_id.create_backorder == 'never':
            return True
        pending = self.product_qty - self.qty_produced
        return float_compare(self.qty_producing, pending,
                             precision_rounding=self.product_uom_id.rounding) >= 0

    def _muc_recompute(self, final=None, diag=None):
        for production in self:
            if production.state not in OPEN_STATES:
                continue
            is_final = production._muc_is_final_close() if final is None else final
            available_by_product = {}
            for move in production.move_raw_ids:
                if move.state in ('done', 'cancel') or not move.product_id:
                    continue
                key = move.product_id.id
                if key not in available_by_product:
                    available_by_product[key] = production._muc_available(move, diag)
                available = available_by_product[key]
                if available is None:  # sin "Transferido totalmente"
                    qty = 0.0
                elif is_final:
                    qty = available
                else:
                    native = (production.qty_producing - production.qty_produced) * move.unit_factor
                    qty = min(max(native, 0.0), available)
                qty = production._muc_round(max(qty, 0.0), move.product_uom)
                if available is not None:
                    available_by_product[key] = max(available - qty, 0.0)
                if diag is not None:
                    diag.append("   → %s: %s → Cantidad hecha = %.2f %s (antes: %.2f)" % (
                        move.product_id.display_name,
                        "cierre final (todo lo disponible)" if is_final else "cierre parcial (proporción LdM)",
                        qty, move.product_uom.name, move.quantity))
                production._muc_apply(move, qty)

    def _muc_available(self, raw_move, diag=None):
        """Disponible del componente para el grupo, en la UdM del movimiento
        de componente. None si no se cumple "Transferido totalmente"."""
        self.ensure_one()
        product = raw_move.product_id
        uom = raw_move.product_uom
        name = product.display_name
        group = raw_move.group_id or self.procurement_group_id
        if not group:
            if diag is not None:
                diag.append("• %s: la orden no tiene grupo de abastecimiento → 0" % name)
            return None
        Move = self.env['stock.move']

        def qty(move):
            return move.product_uom._compute_quantity(move.quantity, uom, round=False)

        transfers = Move.search([
            ('product_id', '=', product.id),
            ('group_id', '=', group.id),
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
            ('raw_material_production_id.procurement_group_id', '=', group.id),
        ]
        scrapped = sum(qty(m) for m in Move.search(group_mo_domain + [('scrapped', '=', True)]))
        consumed = sum(qty(m) for m in Move.search(group_mo_domain + [('scrapped', '=', False)]))
        available = max(sent - returned - scrapped - consumed, 0.0)
        if diag is not None:
            diag.append("• %s: enviado %.2f − devuelto %.2f − desechado %.2f − ya consumido %.2f "
                        "= disponible %.2f %s" % (name, sent, returned, scrapped, consumed,
                                                   available, uom.name))
        return available

    def _muc_round(self, qty, uom):
        digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        return float_round(float_round(qty, precision_rounding=uom.rounding),
                           precision_digits=digits, rounding_method='HALF-UP')

    def _muc_apply(self, move, qty):
        if not isinstance(move.id, int):  # vista previa en el formulario
            if float_compare(move.quantity, qty, precision_rounding=move.product_uom.rounding):
                move.quantity = qty
            return
        if float_compare(move.quantity, qty, precision_rounding=move.product_uom.rounding):
            move.with_context(force_manual_consumption=True).quantity = qty
        # Igual que cuando el usuario digita la cantidad: Odoo consume
        # exactamente esto al producir y no lo cambia por la proporción LdM.
        extra = {}
        if not move.manual_consumption:
            extra['manual_consumption'] = True
        if qty:
            extra['picked'] = True
        if extra:
            move.write(extra)


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
