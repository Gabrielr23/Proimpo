# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import DEFAULT_SERVER_DATE_FORMAT,DEFAULT_SERVER_DATETIME_FORMAT
import time
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import odoo.tools


class HrContractLiquidation(models.Model):
    _name = 'hr.contract.liquidation'
    _description = 'Liquidación de contrato'
    _order = 'date_liquidacion desc'

    name = fields.Char('Nombre', required=True)
    company_id = fields.Many2one('res.company', readonly=False, default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(string="Moneda", related='company_id.currency_id', readonly=True)
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True, ondelete='restrict')
    identification_id = fields.Char(related="employee_id.identification_id", string='Identificación')
    contract_id = fields.Many2one('hr.contract', string='Contrato', readonly=False)
    wage = fields.Monetary('Salario básico', related="contract_id.wage")
    date_start = fields.Date('Fecha ingreso', related="contract_id.date_start", readonly=True)
    average = fields.Boolean('Salario variable', required=True, default=False)
    date_liquidacion = fields.Date('Fecha de liquidación')
    date_vacation = fields.Date('Fecha inicio vacaciones')
    motivo_retiro = fields.Char('Motivo retiro', required = False)
    indemnizacion = fields.Boolean('Calcular indemnización', required=True, default=False)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Aprobada'),
        ('cancel', 'Anulada'),
    ], string='Estado', readonly=True, copy=False, default='draft',
        help="Estado de la liquidación")
    details_ids = fields.One2many('hr.contract.liquidation.details', 'liquidation_id', 'Detalle cálculo', readonly=True)
    slip_id = fields.Many2one('hr.payslip', 'Nómina asociada', ondelete='restrict')
    novedades_count = fields.Integer(compute='_compute_novedades_number', string='Número de novedades')    
    type_contract = fields.Selection([
        ('I', 'Indefinido'),
        ('F', 'Fijo'),
    ], string='Tipo contrato', default='I',
        help="Tipo de contrato para calcular la indemnización")
    contract_end_date = fields.Date(string='Fcha de Finalización contrato fijo')
    total_liquidation = fields.Monetary(compute='_compute_total_liquidation', string='Total')

    @api.depends('details_ids')
    def _compute_novedades_number(self):
        for liq in self:
            novedades = []
            for line in liq.details_ids:
                if line.novedad_id:
                   novedades.append(line.novedad_id.id) 

            liq.novedades_count = len(novedades)

    @api.depends('details_ids')
    def  _compute_total_liquidation(self):
        for liq in self:
            total = 0
            for line in liq.details_ids:
                total += line.amount

            liq.total_liquidation = total

    @api.model
    def create(self, vals):
        if vals.get('employee_id'):
            employee_id = self.env['hr.employee'].sudo().browse([vals.get('employee_id')])
            vals['name'] = employee_id[0].name 
        
        return super().create(vals)

    @api.onchange('employee_id', 'date_liquidacion')
    def _get_contract(self):
        for liq in self:
            liq.details_ids.unlink()
            if liq.date_liquidacion and liq.employee_id:
               liq.contract_id = liq.employee_id.get_contract(liq.date_liquidacion)

               if not liq.contract_id:
                  raise ValidationError('No se encuentra un contrato activo para el empleado hcl %s' % (liq.employee_id.name,))

               liq.contract_end_date = liq.contract_id.contract_end_date
               liq.date_vacation = liq.contract_id.date_start
            else:
               liq.contract_id = False 
               liq.contract_end_date = False
               liq.date_vacation = False

    def action_calculate(self):
        for liq in self:
            # Crea cada concepto a liquidar
            concept_ids = self.env['hr.payslip.input.type'].sudo().search([('liquidation_type','in',['V','C','IC','P','I'])])
            if not concept_ids:
               raise ValidationError('No han configurado los tipos de liquidación en Otros tipos de entrada') 

            if not liq.date_vacation:
               raise ValidationError('No han ingresado la fecha de inicio para el calcuo de la vacaciones')

            # Borra los calculos anteriores
            liq.details_ids.unlink()

            for concept in concept_ids:

                if concept.liquidation_type == 'I' and not liq.indemnizacion:
                   continue 

                vals = {
                   'liquidation_id': liq.id,
                   'employee_id': liq.employee_id.id,
                   'contract_id': liq.contract_id.id,
                   'average': liq.average,
                   'input_type_id': concept.id,
                   'liquidation_type': concept.liquidation_type,
                   'date_to': liq.date_liquidacion,
                }    
                detail_id = self.env['hr.contract.liquidation.details'].create(vals)
                detail_id._calculo_campos()



    def action_confirm(self):
        for liq in self:
            liq.state = 'done'

    def action_create_novedades(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("hr_holidays_co.action_create_novedades_wizard")
        return action


    def action_cancel(self):
        for liq in self:
            if liq.novedades_count > 0:
               # Elimina las novedades asociadas
               for line in self.details_ids:
                   if line.novedad_id:
                      line.novedad_id.sudo().unlink()

               # Si tiene nómina generada y está en borrador, entonces la recalcula
               if liq.slip_id and liq.slip_id.state == 'draft': 
                  liq.slip_id.compute_sheet()    

            liq.state = 'cancel'

    def action_draft(self):
        for liq in self:
            liq.state = 'draft'

    def show_novedades(self):
        self.ensure_one()
        novedades = []
        for line in self.details_ids:
            if line.novedad_id:
               novedades.append(line.novedad_id.id) 

        form_view_ref = self.env.ref('hr_payroll_co.hr_novedades_view', False)
        tree_view_ref = self.env.ref('hr_payroll_co.hr_novedades_tree', False)
        if novedades:
           return {
               'name': 'Novedades de liquidación de contrato',
               'view_mode': 'tree, form',
               'view_id': False,
               'view_type': 'form',
               'res_model': 'hr.novedades',
               'type': 'ir.actions.act_window',
               'target': 'current',
               'domain': "[('id', 'in', %s)]" % novedades,
               'views': [(tree_view_ref and tree_view_ref.id or False, 'tree'), (form_view_ref and form_view_ref.id or False, 'form')],
               'context': {}
           }


    def unlink(self):
        for liq in self:
            if liq.state != 'draft':
              raise UserError('No se permite eliminar la liquidación de %s porque no se encuentra en estado Borrador' % (liq.name,))
        
        return super(HrContractLiquidation, self).unlink()


class HrContractLiquidationDetails(models.Model):
    _name= 'hr.contract.liquidation.details'
    _description = 'Detalle de la liquidación'
    _order = 'liquidation_type'


    company_id = fields.Many2one('res.company', readonly=False, default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(string="Moneda", related='company_id.currency_id', readonly=True)
    liquidation_id = fields.Many2one('hr.contract.liquidation', 'Liquidación', required=False, ondelete='cascade')  
    consolidated_id = fields.Many2one('hr.liquidation.consolidated', 'Liquidación consolidado', required=False, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True, ondelete='restrict', readonly=True)
    contract_id = fields.Many2one('hr.contract', string='Contrato', readonly=True, ondelete='restrict')
    input_type_id = fields.Many2one('hr.payslip.input.type','Parámetro regla',required=False, ondelete='restrict')  
    liquidation_type = fields.Selection([('V','Vacaciones'),
                                         ('C','Cesantías'),
                                         ('IC','Intereses de cesantías'),
                                         ('P','Prima'),
                                         ('I','Indemnización')],
                                       'Concepto', required=True)
    date_from = fields.Date('F. inicial', compute="_calculo_campos", store=True)
    date_to = fields.Date('F. final', required=True)
    days_total = fields.Float('Días', compute="_calculo_campos", store=True)
    days_leave = fields.Float('Ausencias', compute="_calculo_campos", store=True)
    days_neto = fields.Float('Neto días', compute="_calculo_campos", store=True)
    wage_actual = fields.Monetary('Salario básico', compute="_calculo_campos", store=True)
    average = fields.Boolean('Calcular Salario variable', required=True, default=False)
    wage_total = fields.Monetary('Salario variable', compute="_calculo_campos", store=True)
    previou_wage_total = fields.Monetary('Nóminas anteriores', compute="_calculo_campos", store=True)
    days_average = fields.Integer('Días', compute="_calculo_campos", store=True)
    wage_average = fields.Monetary('Promedio', compute="_calculo_campos", store=True)
    subsidio_transporte = fields.Monetary('Sub. transporte', compute="_calculo_campos", store=True)
    total_average = fields.Monetary('Base', compute="_calculo_campos", store=True)
    amount = fields.Monetary('Neto', required=True, default=0)
    provision = fields.Monetary('Provisóin', required=True, default=0)
    ajuste = fields.Monetary('Ajuste', required=True, default=0)
    payslip_line_ids = fields.Many2many('hr.payslip.line', 'contract_liquidation_payslip_rel', 'liquidation_line_id', 'payslip_line_id',
                                        string="Líneas de nómina")
    previous_payslip_ids = fields.Many2many('hr.previous.payrolls', 'contract_liquidation_previous_payslip_rel', 'liquidation_line_id', 'previous_payslip_id',
                                        string="Nóminas anteriores")   
    provisiones_ids = fields.Many2many('hr.payslip.line', 'contract_liquidation_provisiones_rel', 'liquidation_line_id', 'payslip_line_id',
                                        string="Líneas de provisiones")    
    previous_provisiones_ids = fields.Many2many('hr.previous.payrolls', 'contract_liquidation_previous_provisiones_rel', 'liquidation_line_id', 'previous_payslip_id',
                                        string="Provisiones anteriores")                                                                               
    novedad_id = fields.Many2one('hr.novedades', string="Novedades")
    novedad_provision_id = fields.Many2one('hr.novedades', string="Novedades provisiones")
    slip_id = fields.Many2one('hr.payslip', 'Nómina', ondelete='restrict', related='liquidation_id.slip_id')

    @api.depends('liquidation_type','date_to')
    def _calculo_campos(self):

        for line in self:
            # Valores por defecto
            line.wage_total = 0
            previou_wage_total = 0
            line.days_average = 0
            line.wage_average = 0
            line.subsidio_transporte = 0
            if line.liquidation_id:
               line.date_to = line.liquidation_id.date_liquidacion

            if line.consolidated_id:   
               line.date_to = line.consolidated_id.date_liquidation 

            # Subsidio de transporte y salario mínimo del año actual
            subsidio_vigente = self.env['hr.rule.parameter']._get_parameter_from_code('SUBSIDIO_TRANSPORTE', line.date_to)
            salario_vigente = self.env['hr.rule.parameter']._get_parameter_from_code('SALARIO_MINIMO', line.date_to)

            #  Calcula fecha de inicio de cesantías, prima y vacaciones
            if line.liquidation_type == 'V': 
               if line.liquidation_id and not line.date_from:                
                  if line.liquidation_id.date_vacation: 
                     line.date_from = line.liquidation_id.date_vacation 
                  else:
                     line.date_from = line.contract_id.date_start   
                  
               if line.consolidated_id:   
                  if line.consolidated_id.date_vacaciones:   
                     line.date_from = line.consolidated_id.date_vacaciones
                  else:  
                     line.date_from = line.contract_id.date_start 

            if line.liquidation_type in ('C','IC'):
               fecha_cesantias = line.date_to.replace(day=1).replace(month=1)
               if line.contract_id.date_start < fecha_cesantias:
                  line.date_from = fecha_cesantias
               else:
                  line.date_from = line.contract_id.date_start   

            if line.liquidation_type == 'P':
               if line.date_to > line.date_to.replace(day=1).replace(month=7):
                  fecha_prima = line.date_to.replace(day=1).replace(month=7)
               else:
                  fecha_prima = line.date_to.replace(day=1).replace(month=1) 

               if fecha_prima > line.contract_id.date_start:
                  line.date_from = fecha_prima
               else: 
                  line.date_from = line.contract_id.date_start

            # indemnización
            if line.liquidation_type == 'I':   
               line.date_from = line.date_to
  
            # Calcula el promedio salarial solo si se parametriza como variable
            if line.average:
               # Se calcula como todo lo recibido en el periodo 
               line.wage_actual =  0
               line.wage_total = line.sum_categoria_basico(line.date_from)
               line.previou_wage_total = line.sum_categoria_basico_anteriores(line.date_from)
               line.wage_total = line.wage_total + line.previou_wage_total

            else:
               # Se calcula como Salario básico + Promedio salarial 
               line.wage_actual = line.contract_id.wage

               #date_from_average = line.date_to - relativedelta(months=3)
               line.wage_total = line.sum_salario_variable(line.date_from)
               line.previou_wage_total = line.sum_nominas_anteriores(line.date_from)
               line.wage_total = line.wage_total + line.previou_wage_total

            #line.days_average = line.days_between(date_from_average, line.date_to)
            line.days_average = line.days_between(line.date_from, line.date_to) 
            if line.days_average != 0:
               line.wage_average = round((line.wage_total / line.days_average) * 30)

            # Si el empleado vive en el mismo lugar de trabajo, no se le paga subsidio de transporte
            lugar_trabajo = line.contract_id._get_rule_parameter('LUGAR_TRABAJO', line.date_to)
            if lugar_trabajo:
               line.subsidio_transporte = 0 
            else:
               # la base se toma si es salario variable o salario fijo    
               if line.average:
                  if line.wage_average < salario_vigente * 2 and line.liquidation_type in ('P','C','IC'):
                     line.subsidio_transporte = subsidio_vigente
               else:    
                  if (line.wage_actual + line.wage_average) < salario_vigente * 2 and line.liquidation_type in ('P','C','IC'):
                     line.subsidio_transporte = subsidio_vigente

            dias_sancion = 0
            leave_ids_sn = self.env['hr.holidays.report'].sudo().search([('reason_leave','=','sanction'),('contract_id','=',line.contract_id.id)])
            for leave in leave_ids_sn:
                if leave.state == 'validate':
                   dias_sancion += leave.number_of_days

            line.days_leave = dias_sancion

            # Vacaciones
            if line.liquidation_type == 'V':
               line.days_total = line.compute_holidays_pending()
            else:
               line.days_total = line.days_between(line.date_from, line.date_to) 
            
            line.days_neto = line.days_total - line.days_leave

            line.total_average = line.wage_actual + line.wage_average + line.subsidio_transporte    

            if line.liquidation_type == 'P':
               line.amount =  round((line.total_average * line.days_neto)/360)
            elif line.liquidation_type == 'C':
               line.amount = round((line.total_average * line.days_neto)/360)
            elif line.liquidation_type == 'IC':
               line.amount = round((line.total_average * line.days_neto * 0.12)/360)
            elif line.liquidation_type == 'V':
               line.amount = round((line.total_average/30) * line.days_neto)
            elif line.liquidation_type == 'I':
               line.days_average = 0 
               if line.liquidation_id.type_contract == 'F':
                  # Contrato a termino fijo
                  dias_terminacion = line.days_between(line.date_to, line.liquidation_id.contract_end_date)
                  line.date_from = line.date_to
                  line.date_to = line.liquidation_id.contract_end_date
                  line.days_total = dias_terminacion
                  line.days_neto = line.days_total - line.days_leave
                  line.wage_actual = line.contract_id.wage
                  line.amount = round((line.wage_actual/30) * line.days_neto)
               else:
                  # Contrato a termino indefinido 
                  dias_laborados = line.days_between(line.liquidation_id.date_start, line.date_to)
                  line.date_from = line.liquidation_id.date_start
                  line.date_to = line.date_to
                  line.wage_actual = line.contract_id.wage
                  # Si el salario es menos de 10 salarios mínimos
                  if line.wage_actual < (salario_vigente * 10):
                     if dias_laborados < 360:
                        dias_indemnizacion = 30
                     else:
                        # por el primer año se dan 30 días y 20 días por cada año sucesivo
                        dias_laborados = dias_laborados - 360
                        dias_indemnizacion = 30 + ((dias_laborados / 360) * 20)
                  else:  
                     if dias_laborados < 360:
                        dias_indemnizacion = 20
                     else:
                        # por el primer año se dan 20 días y 15 días por cada año sucesivo
                        dias_laborados = dias_laborados - 360
                        dias_indemnizacion = 20 + ((dias_laborados / 360) * 15)

                  line.days_total = dias_indemnizacion
                  line.days_neto = line.days_total - line.days_leave
                  line.amount = round((line.wage_actual/30) * line.days_neto)
                  
            else:
               line.amount = 0  

            # Busca la provisión

            line.provision = line.sum_provisiones(line.date_from) + line.sum_provisiones_anteriores(line.date_from)
            line.ajuste =  line.amount - line.provision  

    @api.model
    def days_between(self, start_date, end_date):
        if not start_date or not end_date:
           return 0.00

        #Add 1 day to end date to solve different last days of month
        s1, e1 =  start_date , end_date + timedelta(days=1)
        #Convert to 360 days

        s360 = (s1.year * 12 + s1.month) * 30 + s1.day
        e360 = (e1.year * 12 + e1.month) * 30 + e1.day

        #Count days between the two 360 dates and return tuple (months, days)
        res = divmod(e360 - s360, 30)

        return ((res[0] * 30) + res[1]) or 0.00

    @api.model
    def compute_holidays_pending(self):
        # Calcula los días de vacaciones pendientes al día de hoy

        for record in self:
            dias_totales = self.days_between(record.date_from, record.date_to)
            vacaciones_tomadas = 0
            sanciones = 0

            leave_ids_vc = self.env['hr.holidays.report'].sudo().search([('reason_leave','=','vacation'),('contract_id','=',record.contract_id.id)])
            for vc in leave_ids_vc:
                if vc.state == 'validate':
                    vacaciones_tomadas += vc.number_of_days_real

            leave_ids_sn = self.env['hr.holidays.report'].sudo().search([('reason_leave','=','sanction'),('contract_id','=',record.contract_id.id)])        
            for sn in leave_ids_sn:
                if sn.state == 'validate':
                    sanciones += sn.number_of_days

            dias_neto = dias_totales - (sanciones * -1)
            dias_vacaciones = float((dias_neto * 15.00) / 360.00)
            dias_pendientes = dias_vacaciones - (vacaciones_tomadas)

            return dias_pendientes

    @api.model
    def sum_salario_variable(self, date_from):
        total = 0
        if self.liquidation_type == 'V':
           # Para Vacaciones
           self.env.cr.execute("""
                       select l.id as line_id, l.amount from hr_payslip_line l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       inner join hr_payslip p on (p.id = l.slip_id)
                       where l.contract_id = %(contrato)s
                         and r.average_salary_vacation = True
                         and p.state <> 'cancel'
                         and p.date_from between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'contrato': self.contract_id.id,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

        else:   
           # Para Prima y Cesantías
           self.env.cr.execute("""
                       select l.id as line_id, l.amount from hr_payslip_line l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       inner join hr_payslip p on (p.id = l.slip_id)
                       where l.contract_id = %(contrato)s
                         and r.average_salary = True
                         and p.state <> 'cancel'
                         and p.date_from between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'contrato': self.contract_id.id,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

        result = self.env.cr.fetchall()  
        if result:
           for line in result: 
               total += line[1]
           
           self.payslip_line_ids = [row[0] for row in result]

        return total

    @api.model
    def sum_categoria_basico(self, date_from):
        total = 0
        if self.liquidation_type == 'V':
           # Para Vacaciones
           self.env.cr.execute("""
                       select l.id as line_id, l.amount from hr_payslip_line l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       inner join hr_payslip p on (p.id = l.slip_id)
                       inner join hr_salary_rule_category g on (g.id = r.category_id)
                       where l.contract_id = %(contrato)s
                         and g.code = 'BASICO'
                         and p.state <> 'cancel'
                         and p.date_from between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'contrato': self.contract_id.id,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

        else:  
           # Para Prima y Cesantías         
           self.env.cr.execute("""
                       select l.id as line_id, l.amount from hr_payslip_line l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       inner join hr_payslip p on (p.id = l.slip_id)
                       inner join hr_salary_rule_category g on (g.id = r.category_id)
                       where l.contract_id = %(contrato)s
                         and g.code = 'BASICO'
                         and p.state <> 'cancel'
                         and p.date_from between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'contrato': self.contract_id.id,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

        result = self.env.cr.fetchall()  
        if result:
           for line in result: 
               total += line[1]
           
           self.payslip_line_ids = [row[0] for row in result]

        return total

    @api.model
    def sum_categoria_basico_anteriores(self, date_from):
        total = 0
        if self.liquidation_type == 'V':
           # Para Vacaciones    
           self.env.cr.execute("""
                       select l.id as line_id, l.value 
                       from hr_previous_payrolls l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       inner join hr_salary_rule_category g on (g.id = r.category_id)
                       where l.employee_id = %(empleado)s
                         --and r.liquidation_type
                         and g.code = 'BASICO'
                         and l.date between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'empleado': self.employee_id.id,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

        else:       
           # Para Prima y Cesantías
           self.env.cr.execute("""
                       select l.id as line_id, l.value 
                       from hr_previous_payrolls l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       inner join hr_salary_rule_category g on (g.id = r.category_id)
                       where l.employee_id = %(empleado)s
                         and g.code = 'BASICO'
                         and l.date between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'empleado': self.employee_id.id,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

        result = self.env.cr.fetchall()  
        if result:
           for line in result: 
               total += line[1]
           
           self.previous_payslip_ids = [row[0] for row in result]

        return total         


    @api.model
    def sum_nominas_anteriores(self, date_from):
        total = 0
        if self.liquidation_type == 'V':
           # Para Vacaciones    
           self.env.cr.execute("""
                       select l.id as line_id, l.value 
                       from hr_previous_payrolls l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       where l.employee_id = %(empleado)s
                         and r.liquidation_type
                         and l.date between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'empleado': self.employee_id.id,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

        else:       
           # Para Prima y Cesantías
           self.env.cr.execute("""
                       select l.id as line_id, l.value 
                       from hr_previous_payrolls l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       where l.employee_id = %(empleado)s
                         and r.average_salary = True
                         and l.date between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'empleado': self.employee_id.id,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

        result = self.env.cr.fetchall()  
        if result:
           for line in result: 
               total += line[1]
           
           self.previous_payslip_ids = [row[0] for row in result]

        return total         

    @api.model
    def sum_provisiones(self, date_from):
        total = 0
        if self.liquidation_type in ('C','IC','P','V'):
        
           # Busca las provisiones
           self.env.cr.execute("""
                       select l.id as line_id, l.amount from hr_payslip_line l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       inner join hr_payslip p on (p.id = l.slip_id)
                       where l.contract_id = %(contrato)s
                         and r.liquidation_type = %(tipo)s
                         and p.state <> 'cancel'
                         and p.date_from between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'contrato': self.contract_id.id,
                                'tipo': 'P'+self.liquidation_type,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

           result = self.env.cr.fetchall()  
           if result:
              for line in result: 
                  total += line[1]
           
              self.provisiones_ids = [row[0] for row in result]

        return total


    @api.model
    def sum_provisiones_anteriores(self, date_from):
        total = 0
        if self.liquidation_type in ('C','IC','P','V'):
           # Para Vacaciones    
           self.env.cr.execute("""
                       select l.id as line_id, l.value 
                       from hr_previous_payrolls l
                       inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                       where l.employee_id = %(empleado)s
                         and r.liquidation_type = %(tipo)s
                         and l.date between %(fecha_inicial)s and %(fecha_final)s
                         """,  {'empleado': self.employee_id.id,
                                'tipo': 'P'+self.liquidation_type,
                                'fecha_inicial': date_from,
                                'fecha_final': self.date_to,
                               })   

        result = self.env.cr.fetchall()  
        if result:
           for line in result: 
               total += line[1]
           
           self.previous_provisiones_ids = [row[0] for row in result]

        return total         

