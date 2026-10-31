# -*- coding: utf-8 -*-
"""Decisión A: el producto manda.

Todo producto de la categoría `All / Materias Primas / Moldes` tiene un
equipo-molde en Mantenimiento. El equipo se crea solo cuando el producto
nace (o cuando se le cambia la categoría a Moldes); los productos que ya
existían se generan con el asistente de Moldes → Configuración.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _mold_ensure_equipment(self):
        """Crea (o vincula) el equipo-molde de los productos que estén en la
        categoría de moldes. Devuelve el resumen de lo ocurrido."""
        Equipment = self.env['maintenance.equipment'].sudo()
        cats = Equipment._mold_category_ids()
        if not cats:
            return {}
        productos = self.filtered(
            lambda p: p.categ_id.id in cats and p.active)
        if not productos:
            return {}
        return Equipment._create_from_products(productos)

    @api.model_create_multi
    def create(self, vals_list):
        productos = super().create(vals_list)
        if not self.env.context.get('mold_skip_autocreate'):
            try:
                with self.env.cr.savepoint():
                    productos._mold_ensure_equipment()
            except Exception as e:  # noqa: BLE001
                # Crear un producto nunca debe fallar por culpa del molde.
                _logger.warning(
                    'No se pudo crear el equipo-molde del producto: %s', e)
        return productos


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        res = super().write(vals)
        if ('categ_id' in vals
                and not self.env.context.get('mold_skip_autocreate')):
            try:
                with self.env.cr.savepoint():
                    self.product_variant_ids._mold_ensure_equipment()
            except Exception as e:  # noqa: BLE001
                _logger.warning(
                    'No se pudo crear el equipo-molde al cambiar la '
                    'categoría: %s', e)
        return res
