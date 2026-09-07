# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    # MIGRACION 19.0: se elimina el _description. En un modelo heredado
    # (_inherit) el _description sobrescribe la descripcion del modelo del
    # core ('Production Order'), lo que no era la intencion.

    @api.onchange('qty_producing')
    def _onchange_qty_producing(self):
        _logger.debug('_onchange_qty_producing')

        for move_line in self.move_raw_ids:
            _logger.debug('MOVE RAW ----------------------------------%s', move_line)
            product_id = move_line.product_id.id
            if not product_id:
                # MIGRACION 19.0: en el codigo original move_stock /
                # move_stock_all se calculaban dentro de un "if" pero se
                # usaban fuera de el; si un movimiento no tenia producto se
                # levantaba NameError (o se reutilizaban los valores de la
                # iteracion anterior). Se corrige saltando la linea.
                continue

            # MIGRACION 19.0: el modelo 'procurement.group' y el campo
            # stock.move.group_id fueron ELIMINADOS en Odoo 19. El enlace
            # entre la orden de produccion y sus transferencias es ahora
            # 'stock.reference' via stock.move.reference_ids (Many2many).
            # Ver addons/stock/models/stock_reference.py y
            # addons/mrp/models/stock_move.py (rama 19.0), donde mrp propaga
            # production_id.reference_ids a los movimientos.
            reference_ids = move_line.reference_ids.ids

            move_stock = self.env['stock.move'].search([
                                                        ('product_id', '=', product_id),
                                                        ('reference_ids', 'in', reference_ids),
                                                        ('state', '=', 'done'),
                                                        ('picking_type_id.code', '=', 'internal'),
                                                        ('picking_type_id.consumed', '=', True),
                                                        ('to_refund', '=', False)
                                                       ], order="date desc", limit=1)
            _logger.debug('MOVE_STOCK -------------------------- %s', move_stock)

            move_stock_all = self.env['stock.move'].search([
                                                            ('product_id', '=', product_id),
                                                            ('picking_type_id.consumed', '=', True),
                                                            ('reference_ids', 'in', reference_ids),
                                                            ('state', '=', 'done'),
                                                           ])

            qty_consumed = self.move_stock_no_done(product_id, reference_ids) or 0

            if move_stock.picking_id.totally_transferred:
                _logger.debug('TOTAL TRANSFERENCIA %s', move_stock.picking_id.totally_transferred)
                qty_all = 0
                for move_all in move_stock_all:
                    if move_all.picking_type_id.code == 'internal' and move_all.to_refund != True:
                        qty_all += move_all.quantity
                    elif move_all.picking_type_id.code == 'internal' and move_all.to_refund == True:
                        qty_all -= move_all.quantity
                    elif move_all.picking_type_id.code == 'mrp_operation' or move_all.to_refund == True:
                        qty_all -= move_all.quantity

                _logger.debug('VALORES ------------------------------- %s move %s', qty_all, move_line.quantity)
                if qty_all != move_line.quantity:
                    move_line.quantity = round((((qty_all - qty_consumed) / self.product_qty) * self.qty_producing), 2)

    def button_mark_done(self):

        if self.qty_producing == 0:
            raise ValidationError(_("Debe poner un valor mayor a 0 en cantidad."))

        #self._onchange_qty_producing()
        return super().button_mark_done()

    def move_stock_no_done(self, product_id, reference_ids):
        # MIGRACION 19.0: la firma cambia de (product_id, group_id) a
        # (product_id, reference_ids) por la eliminacion de procurement.group.
        move_stock = self.env['stock.move'].search([('product_id', '=', product_id),
                                                    ('reference_ids', 'in', reference_ids),
                                                    ('state', '=', 'done'),
                                                    ('picking_type_id.code', '=', 'mrp_operation'),
                                                    ('to_refund', '=', False)
                                                   ])

        qty = 0
        for move in move_stock:
            qty += move.quantity
        return qty


class MrpProductionWorkcenterLine(models.Model):
    _inherit = "mrp.workorder"

    # ATENCION - REQUIERE VERIFICACION MANUAL:
    # 'progress' YA EXISTE en el core (addons/mrp/models/mrp_workorder.py,
    # ramas 18.0 y 19.0) como:
    #     progress = fields.Float('Progress Done (%)', digits=(16, 2),
    #                             compute='_compute_progress')
    # Esta redefinicion SUSTITUYE el compute del core. La unica diferencia
    # funcional es que el core fuerza 100 cuando state == 'done' y esta
    # version no. Se conserva el comportamiento original del modulo.
    #
    # MIGRACION 19.0: se corrige digits de (3, 2) a (16, 2). Con (3, 2) el
    # valor maximo representable era 9.99, por lo que cualquier avance
    # superior al 10% quedaba mal representado.
    progress = fields.Float(string="Progreso (%)", compute='_progress_time', digits=(16, 2))

    # MIGRACION 19.0: se agrega 'duration_expected' a los depends; el compute
    # lo lee pero no estaba declarado, por lo que no se recalculaba al
    # cambiar la duracion esperada.
    @api.depends('duration', 'duration_expected')
    def _progress_time(self):

        for line in self:
            if line.duration > 0.0 and line.duration_expected > 0.0:
                line.progress = (line.duration / line.duration_expected) * 100
            else:
                line.progress = 0.0
