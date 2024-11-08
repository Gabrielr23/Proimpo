# -*- coding: utf-8 -*-

from odoo import models, fields, api


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    _description = 'Actualiza los valores consumidos desde los picking de transferencia'
   
    @api.onchange('qty_producing')
    def _onchange_qty_producing(self):

    

        for move_line in self.move_raw_ids:
            product_id = move_line.product_id.id
            group_id = move_line.group_id.id  
            if move_line.product_id.id :

                move_stock = self.env['stock.move'].search([
                                                            ('product_id' , '=' , product_id),
                                                            ('group_id' , '=', group_id),
                                                            ('state' , '=' , 'done'),
                                                            ('picking_type_id.code' , '=' , 'internal'),
                                                            ('to_refund' , '=' , False)
                                                           ],order="date desc",limit=1)

                
                move_stock_all = self.env['stock.move'].search([
                                                                ('product_id' , '=' , product_id),
                                                                ('group_id' , '=', group_id),
                                                                ('state' , '=' , 'done')
                                                               ])                                           
    
            if move_stock.picking_id.totally_transferred:
                qty_all = 0

                for move_all in move_stock_all:
                    if move_all.picking_type_id.code == 'internal' and move_all.to_refund != True:
                        qty_all += move_all.product_qty
                    elif move_all.picking_type_id.code == 'mrp_operation' or move_all.to_refund == True: 
                        qty_all -= move_all.product_qty
                    
                if qty_all != move_line.quantity_done:
                    move_line.quantity_done = round(((qty_all / self.product_qty) * self.qty_producing),4)

            
                
class MrpProductionWorkcenterLine(models.

Model):
    _inherit = "mrp.workorder"

    progress = fields.Float(string="Progreso (%)", compute='_progress_time', digits=(3,2))
    
    @api.depends('duration')
    def _progress_time(self):

        for line in self:
            if line.duration > 0:
                line.progress = (line.duration / line.duration_expected) * 100 or 0
            else:
                line.progress = 0


        return       
       



