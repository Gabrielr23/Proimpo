# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, RedirectWarning
from odoo.tools.misc import formatLang, format_date
from datetime import date, datetime, time, timedelta



class PaymentExportWizard(models.TransientModel):
    
    _name = "payment.export.wizard"
    _description = "Genera plano bancos Colombia"

   
    date_payment = fields.Date(string="Fecha Pago", required=True, default=fields.Date.context_today)
    date_application = fields.Date(string="Fecha aplicacion", required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Diario', required=True, domain="[('company_id', '=', company_id), ('type', 'in', ('bank'))]")
    transaccion = fields.Selection(string='Tipo de Transaccion', requires=True, selection=[('220','220 - Pago a Proveedores'),
                                                                                           ('221','221 - Pago a Proveedores'),
                                                                                           ('225','225 - Pago de Nomina'),
                                                                                           ('226','226 - Pago de Nomina'),
                                                                                           ('238','238 - Pago Terceros')], default='220 - Pago a Proveedores')
    descripcion = fields.Char(string='Descripcion', size=10)
    lote = fields.Char(string='Lote', size=2, help='No puede enviarse la misma secuencia un mismo dia Ej. A1,A2...')                                                                                    

    
    #def export_txt(self):

    def _reg_encabezado(self):    
        text_reg_1 = ''
        active_ids = self.env.context.get('active_ids')
        num_reg = len(active_ids)
        total = 0.00
        journal_id = self.journal_id.id
        company_id = self.journal_id.company_id.partner_id
        tipo_cta = self.journal_id.bank_account_id.tipo_cta
        parameter_bank = self.journal_id.bank_id.bank_parameter_ids
        cuenta_debitar = self.journal_id.bank_account_id.acc_number

        for record in self.env['account.payment'].browse(active_ids):
            if record:
                total += record.amount
                print

        if tipo_cta == 'C':
            tipo_cta = 'Corriente'        
        elif tipo_cta == 'A':
            tipo_cta = 'Ahorro'
        elif tipo_cta == 'R':
            tipo_cta = 'Rotativo'  
 

        t_c = ''
        for param in parameter_bank:
            if param.name == tipo_cta:
                t_c =  param.value
                 
        fecha_pago = str(self.date_payment)
        fecha_pago = fecha_pago.replace('-', '')
        fecha_apli = str(self.date_application)
        fecha_apli = fecha_apli.replace('-', '')
        num_reg = str(num_reg)
        total = str(total)
        total = total.replace('.','')
        
        #dia = fecha_pago[6:]
        #mes = fecha_pago[4:6]
        #ano = fecha_pago[:4]
        #fecha_pago = dia + mes + ano

        text_reg_1 += '1' + company_id.ref.zfill(15) + 'I' + (15 * ' ') + self.transaccion + self.descripcion + fecha_pago + self.transaccion + fecha_apli
        text_reg_1 += num_reg.zfill(6) + (17 * ' ') + total.zfill(17) + '0' + cuenta_debitar + t_c
              



        print('text_reg -.-.-.-.-.-.-.-.-.-.-.-.-.-.-.',text_reg_1)  
                
    #def _reg_detalle(self):
    
    def export_txt(self):
        today = datetime.today()
        fecha = today.strftime("%Y-%m-%d-%f")
        filename = 'plano_bancolombia_'+fecha+'.txt'
        file = open("/opt/odoo15/odoo-server/addons-extra/report_sql/static/"+filename, "w")
        
        text_reg_2 = ''
        active_ids = self.env.context.get('active_ids')

        
        for record in self.env['account.payment'].browse(active_ids):
            fecha_pago_2 = str(self.date_payment)
            fecha_pago_2 = fecha_pago_2.replace('-', '')
            fecha_apli_2 = str(self.date_application)
            fecha_apli_2 = fecha_apli_2.replace('-', '')    
            if record:
                name_partner = record.partner_id.name
                id_partner = record.partner_id.ref
                cod_bank = record.partner_bank_id.bank_id.bic
                cta_partner = record.partner_bank_id.acc_number
                parameter_bank_partner = self.journal_id.bank_id.bank_parameter_ids
                tipo_cta_partner = record.partner_bank_id.tipo_cta
                valor = round(record.amount,2)
                transaccion = ' '
                if tipo_cta_partner == 'C':
                    transaccion = 'Abono Corriente'
                elif tipo_cta_partner == 'A':
                    transaccion = 'Abono Ahorro'

                t_t = ' '       
                for param in parameter_bank_partner:
                    if param.name == transaccion:
                        t_t =  param.value
                
                valor = str(valor)
                valor = valor.replace('.','')
                

        


                text_reg_2 += '6' + id_partner.ljust(15, " ") + name_partner.ljust(30, " ") + (5 * '0') + '1' + cod_bank + cta_partner.ljust(17, " ") + ' ' + t_t 
                text_reg_2 += valor.zfill(16)+ '0' + fecha_pago_2 + (21 * ' ')
                print('text_reg 2 -.-.-.-.-.-.-.-.-.-.-.-.-.-.-.',text_reg_2)
                file.write(text_reg_2 + '\n')
                file.write(f'{text_reg_2}\n')


    
    def open_wizard(self):
        return {
            'name': 'Generar Archivo Banco',
            'type': 'ir.actions.act_window',
            'res_model': 'payment.export.wizard',
            'target': 'new',
            'views': [(self.env.ref('generate_bank_file.generate_bank_file_wizard_view').id, 'form')],
            #'view_id': self.env.ref('payment_export_file_bank.payment_export_wizard_view').id,
            #'context': {'active_ids': self.ids},
            'context': {'active_ids': self.env.context.get('active_ids')},
            }


            