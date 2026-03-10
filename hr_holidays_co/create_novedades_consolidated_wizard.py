# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, tools, fields, exceptions, api, _
from odoo.exceptions import ValidationError

class CreateNovedadesConsolidatedWizard(models.TransientModel):
    _name = 'create.novedades.consolidated.wizard'
    _description = 'Crear novedades de consolidados'

    @api.model
    def default_get(self, fields):
        res = super(CreateNovedadesConsolidatedWizard, self).default_get(fields)
        consolidated_id = self.env.context.get('active_id')
        consolidated = self.env['hr.liquidation.consolidated'].browse(consolidated_id)
        if consolidated:

           res.update({'consolidated_id': consolidated.id, 
                       'date_start': consolidated.date_liquidation.replace(day=1), 
                       'date_stop': consolidated.date_liquidation,
                       'liquidation_prima': consolidated.liquidation_prima,
                       'liquidation_cesantias': consolidated.liquidation_cesantias,
                       'liquidation_vacaciones': consolidated.liquidation_vacaciones,
                      })

        return res

    date_start = fields.Date(string="Fecha inicial", required=True)
    date_stop = fields.Date(string="Fecha final", required=True)
    consolidated_id = fields.Many2one('hr.liquidation.consolidated', string='Cálculo prestaciones')
    liquidation_prima = fields.Boolean(string='Calcular prima')
    liquidation_cesantias = fields.Boolean(string='Calcular cesantías e intereses')
    liquidation_vacaciones = fields.Boolean(string='Calcular vacaciones')        
    ajuste_prima = fields.Boolean(string='Ajuste provisión prima', required=True, default=False)
    ajuste_cesantias = fields.Boolean(string='Ajuste provisión cesantías e intereses', required=True, default=False)
    ajuste_vacaciones = fields.Boolean(string='Ajuste provisión vacaciones', required=True, default=False)  

    def create_novedades(self):
        self.create_hr_novedeades()


    @api.model
    def create_hr_novedeades(self):
        self.ensure_one()

        if self.ajuste_prima:
           concept_ids = self.env['hr.payslip.input.type'].sudo().search([('liquidation_type','=','PP')])
           if not concept_ids:
              raise ValidationError('No ha configurado Otro tipo de entrada para Ajuste provisión prima')
           else:
              input_type_prima = concept_ids[0]

        if self.ajuste_cesantias:
           concept_ids = self.env['hr.payslip.input.type'].sudo().search([('liquidation_type','=','PC')])
           if not concept_ids:
              raise ValidationError('No ha configurado Otro tipo de entrada para Ajuste provisión cesantías')
           else:
              input_type_cesantias = concept_ids[0]

           concept_ids = self.env['hr.payslip.input.type'].sudo().search([('liquidation_type','=','PIC')])
           if not concept_ids:
              raise ValidationError('No ha configurado Otro tipo de entrada para Ajuste provisión intereses de cesantía')
           else:
              input_type_intereses = concept_ids[0]

        if self.ajuste_vacaciones:
           concept_ids = self.env['hr.payslip.input.type'].sudo().search([('liquidation_type','=','PV')])
           if not concept_ids:
              raise ValidationError('No ha configurado Otro tipo de entrada para Ajuste provisión vacaciones')
           else:
              input_type_vacaciones = concept_ids[0]
      

        for line in self.consolidated_id.details_ids:
            # No se crean novedades en cero o negativas
            if line.amount <= 0:
               continue 

            vals = {
               'date_from': self.date_start,
               'date_to': self.date_stop,
               'employee_id': line.employee_id.id,
               'value': line.amount,
               'input_id': line.input_type_id.id,

            }
            if line.novedad_id:
               line.novedad_id.write(vals) 
            else:
               novedad_id = self.env['hr.novedades'].sudo().create(vals)
               line.write({'novedad_id': novedad_id.id})
 
            if line.liquidation_type == 'P' and self.ajuste_prima and line.ajuste > 0:
               vals_prov = {
                  'date_from': self.date_start,
                  'date_to': self.date_stop,
                  'employee_id': line.employee_id.id,
                  'value': line.ajuste,
                  'input_id': input_type_prima.id,
               }

               if line.novedad_provision_id:
                  line.novedad_provision_id.write(vals) 
               else:
                  novedad_provision_id = self.env['hr.novedades'].sudo().create(vals_prov)
                  line.write({'novedad_provision_id': novedad_provision_id.id})


            if line.liquidation_type == 'C' and self.ajuste_cesantias and line.ajuste > 0:
               vals_prov = {
                  'date_from': self.date_start,
                  'date_to': self.date_stop,
                  'employee_id': line.employee_id.id,
                  'value': line.ajuste,
                  'input_id': input_type_cesantias.id,
               }

               if line.novedad_provision_id:
                  line.novedad_provision_id.write(vals) 
               else:
                  novedad_provision_id = self.env['hr.novedades'].sudo().create(vals_prov)
                  line.write({'novedad_provision_id': novedad_provision_id.id})

            if line.liquidation_type == 'IC' and self.ajuste_cesantias and line.ajuste > 0:
               vals_prov = {
                  'date_from': self.date_start,
                  'date_to': self.date_stop,
                  'employee_id': line.employee_id.id,
                  'value': line.ajuste,
                  'input_id': input_type_intereses.id,
               }

               if line.novedad_provision_id:
                  line.novedad_provision_id.write(vals) 
               else:
                  novedad_provision_id = self.env['hr.novedades'].sudo().create(vals_prov)
                  line.write({'novedad_provision_id': novedad_provision_id.id})

            if line.liquidation_type == 'V' and self.ajuste_vacaciones and line.ajuste > 0:
               vals_prov = {
                  'date_from': self.date_start,
                  'date_to': self.date_stop,
                  'employee_id': line.employee_id.id,
                  'value': line.ajuste,
                  'input_id': input_type_vacaciones.id,
               }

               if line.novedad_provision_id:
                  line.novedad_provision_id.write(vals) 
               else:
                  novedad_provision_id = self.env['hr.novedades'].sudo().create(vals_prov)
                  line.write({'novedad_provision_id': novedad_provision_id.id})



    def update_payslip(self):
        self.ensure_one()
        # primero busca si el empleado tiene una nómina en borrador
        self.create_hr_novedeades()

        for line in self.consolidated_id.details_ids:
            payslip_ids = self.env['hr.payslip'].sudo().search([('contract_id','=',line.contract_id.id),
                                                               ('date_from','=',self.date_start),
                                                               ('date_to','=',self.date_stop),
                                                               ('state','in',['draft','verify']),
                                                          ])
            for slip in payslip_ids:
                slip.compute_sheet()
                line.write({'slip_id': slip.id})   



