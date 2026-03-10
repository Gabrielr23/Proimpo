# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, tools, fields, exceptions, api, _
from odoo.exceptions import ValidationError

class CreateNovedadesWizard(models.TransientModel):
    _name = 'create.novedades.wizard'
    _description = 'Crear novedades'

    @api.model
    def default_get(self, fields):
        res = super(CreateNovedadesWizard, self).default_get(fields)
        liquidation_id = self.env.context.get('active_id')
        liquidation = self.env['hr.contract.liquidation'].browse(liquidation_id)
        if liquidation:
           if liquidation.slip_id:
              exist_payslip = True
           else:
              exist_payslip = False   

           res.update({'liquidation_id': liquidation.id, 
                       'date_start': liquidation.date_liquidacion, 
                       'date_stop': liquidation.date_liquidacion,
                       'struct_id': liquidation.contract_id.structure_type_id.struct_ids[0].id,
                       'exist_payslip': exist_payslip,
                      })

        return res

    date_start = fields.Date(string="Fecha inicial", required=True)
    date_stop = fields.Date(string="Fecha final", required=True)
    liquidation_id = fields.Many2one('hr.contract.liquidation', string='Liquidación')
    struct_id = fields.Many2one('hr.payroll.structure', string='Estructura salarial')
    exist_payslip = fields.Boolean('Existe nómina', required=True)


    def create_novedades(self):
        self.create_hr_novedeades()


    @api.model
    def create_hr_novedeades(self):
        self.ensure_one()
        for line in self.liquidation_id.details_ids:
            vals = {
               'date_from': self.date_start,
               'date_to': self.date_stop,
               'employee_id': self.liquidation_id.employee_id.id,
               'value': line.amount,
               'input_id': line.input_type_id.id,

            }
            if line.novedad_id:
               line.novedad_id.write(vals) 
            else:
               novedad_id = self.env['hr.novedades'].sudo().create(vals)
               line.write({'novedad_id': novedad_id.id})
 

    def create_payslip(self):
        self.ensure_one()
        # primero crea las novedades
        self.create_hr_novedeades()

        vals = {
               'date_from': self.date_start,
               'date_to': self.date_stop,
               'employee_id': self.liquidation_id.employee_id.id,
               'contract_id': self.liquidation_id.contract_id.id,
               'struct_id': self.struct_id.id,
               'name': 'Liquidación ' + self.liquidation_id.employee_id.name,

            }
        slip_id = self.env['hr.payslip'].sudo().create(vals) 
        slip_id.compute_sheet()
        self.liquidation_id.write({'slip_id': slip_id.id})   



