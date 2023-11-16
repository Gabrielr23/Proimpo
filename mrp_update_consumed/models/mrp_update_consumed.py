# -*- coding: utf-8 -*-

from odoo import models, fields, api


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    _description = 'Actualiza los valores consumidos desde los picking de transferencia'
   
    @api.onchange('qty_producing')
    def _onchange_qty_producing(self):

        for move_line in self.move_raw_ids:
            product_id = move_line.product_id.id
            #qty = move_line.quantity_done
            group_id = move_line.group_id.id  
            if move_line.product_id.id :
                move_stock = self.env['stock.move'].search([
                                                            ('product_id' , '=' , product_id),
                                                            ('group_id' , '=', group_id),
                                                            ('state' , '=' , 'done')   
                                                           ])
                qty_final = 0 
                for move_ult in move_stock:
                    #qty_final = 0
                    qty_final += move_ult.product_qty 
            
                if qty_final != move_line.quantity_done:
                    move_line.quantity_done = qty_final



#class MrpProductionWorkcenterLine(models.Model):
#    _inherit = "mrp.workorder"

#    progress = fields.Float(string="Progreso (%)", compute='_progress_time', digits=(3,2), store=True)
#    #progress = fields.Integer(compute='_progress_time')

#    @api.depends('duration')
#    def _progress_time(self):

#        for line in self:
#            if line.duration > 0:
#                line.progress = (self.duration / self.duration_expected) * 100 or 0
#            else:
#                line.progress = 0
        #    print('percent 1-------------------', percent)


        #return percent       
       



