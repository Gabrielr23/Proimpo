# -*- coding: utf-8 -*-

from odoo import models, fields,  api, _
from odoo.exceptions import UserError, ValidationError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    _description = 'Actualiza los valores consumidos desde los picking de transferencia'

    
    @api.onchange('qty_producing')
    def _onchange_qty_producing(self):
        print('_onchange_qty_producing')
    

        for move_line in self.move_raw_ids:
            product_id = move_line.product_id.id
            group_id = move_line.group_id.id  
            if move_line.product_id.id :

                move_stock = self.env['stock.move'].search([
                                                            ('product_id' , '=' , product_id),
                                                            ('group_id' , '=', group_id),
                                                            ('state' , '=' , 'done'),
                                                            ('picking_type_id.code' , '=' , 'internal'),
                                                            ('picking_type_id.consumed' , '=' , True),
                                                            ('to_refund' , '=' , False)
                                                           ],order="date desc",limit=1)

                move_stock_all = self.env['stock.move'].search([
                                                                ('product_id' , '=' , product_id),
                                                                ('picking_type_id.consumed' , '=' , True),
                                                                ('group_id' , '=', group_id),
                                                                ('state' , '=' , 'done')
                                                               ])
   
            qty_consumed = self.move_stock_no_done(product_id,group_id) or 0
            #print('qty_consumed --------------------------',qty_consumed)
                     
            if move_stock.picking_id.totally_transferred:
                #qty_all = qty_consumed
                qty_all = 0
                for move_all in move_stock_all:
                    if move_all.picking_type_id.code == 'internal' and move_all.to_refund != True and move_all.state != 'done':
                        qty_all += move_all.quantity
                    elif move_all.picking_type_id.code == 'internal' and move_all.to_refund == True:
                        qty_all -= move_all.quantity
                    elif move_all.picking_type_id.code == 'mrp_operation' or move_all.to_refund == True: 
                        qty_all -= move_all.quantity
                    print('move_all.quantity -----------------------',move_all.quantity,'qty_all',qty_all)
                
                if qty_all != move_line.quantity:
                    move_line.quantity = round(((qty_all / self.product_qty) * self.qty_producing),2)
                
    def button_mark_done(self):

        if self.qty_producing == 0:
            raise ValidationError(_("Debe poner un valor mayor a 0 en cantidad."))
            
        #self._onchange_qty_producing()
        return super(MrpProduction, self).button_mark_done()

    def move_stock_no_done(self,product_id,group_id):

        move_stock = self.env['stock.move'].search([('product_id' , '=' , product_id),
                                                    ('group_id' , '=', group_id),
                                                    ('state' , '=' , 'done'),
                                                    ('picking_type_id.code' , '=' , 'mrp_operation')
                                                   ])  
                                                   
                                                             
        print('move_stock ----------------------------',move_stock)
        for move in move_stock:
            qty = move_stock.quantity
            return qty    






class MrpProductionWorkcenterLine(models.Model):
    _inherit = "mrp.workorder"

    progress = fields.Float(string="Progreso (%)", compute='_progress_time', digits=(3,2))

    
    @api.depends('duration')
    def _progress_time(self):

        for line in self:
            if line.duration > 0.0 and line.duration_expected > 0.0:
                line.progress = (line.duration / line.duration_expected) * 100
            else:
                line.progress = 0.0


        return       




