# -*- coding: utf-8 -*-

from odoo import models

from .mrp_production import MUC_SKIP


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    def do_scrap(self):
        """Validar un desecho desde la orden de fabricación recalcula la
        Cantidad hecha de las órdenes abiertas de su grupo."""
        res = super().do_scrap()
        if not self.env.context.get(MUC_SKIP):
            groups = self.production_id.production_group_id
            if groups:
                self.env['mrp.production']._muc_open_productions(groups)._muc_recompute()
        return res
