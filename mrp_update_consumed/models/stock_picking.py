# -*- coding: utf-8 -*-

from odoo import fields, models

from .mrp_production import MUC_SKIP


class StockPicking(models.Model):
    _inherit = "stock.picking"

    totally_transferred = fields.Boolean(
        string="Transferido totalmente",
        help='Debe poner este check si se transfirio todo para la order de producción.')

    def _action_done(self):
        """Validar un Pick Components o una devolución recalcula la Cantidad
        hecha de las órdenes abiertas vinculadas."""
        res = super()._action_done()
        self._muc_recompute_productions()
        return res

    def write(self, vals):
        res = super().write(vals)
        if 'totally_transferred' in vals:
            self._muc_recompute_productions()
        return res

    def _muc_recompute_productions(self):
        if self.env.context.get(MUC_SKIP):
            return
        moves = self.move_ids.filtered(
            lambda m: m.picking_type_id.consumed or m.origin_returned_move_id.picking_type_id.consumed)
        groups = moves.production_group_id
        if groups:
            self.env['mrp.production']._muc_open_productions(groups)._muc_recompute()
