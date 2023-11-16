# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, RedirectWarning
from odoo.tools.misc import formatLang, format_date
from datetime import date, datetime, time, timedelta
import os
#from stat import S_IREAD, S_IRGRP, S_IROTH
#import base64
#import mimetypes



class PaymentExportWizard(models.TransientModel):
    
    _name = "payment.export.wizard"
    _description = "Genera plano bancos Colombia"

   
    date_payment = fields.Date(string="Fecha Pago", required=True, default=fields.Date.context_today)
    date_application = fields.Date(string="Fecha Aplicación", required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Diario', required=True, domain="[('company_id', '=', company_id), ('type', 'in', ('bank'))]")
    transaccion = fields.Selection(string='Tipo de Transaccion', requires=True, selection=[('220','220 - Pago a Proveedores'),
                                                                                           ('225','225 - Pago de Nomina')], default='220')
    descripcion = fields.Char(string='Descripcion', size=12, requires=True)
    sequence = fields.Char(string='Secuencia', size=1, requires=True, help='No puede enviarse la misma secuencia un mismo dia Ej. A,B,C...')
                                                                                   

    
    def export_txt(self):

    

    #def _reg_encabezado(self): 
        today = datetime.today()
        fecha = today.strftime("%Y-%m-%d-%f")
        path = self.env['ir.config_parameter'].get_param("home.odoo.repo")
        #filename = 'plano_bancolombia_'+fecha+'.csv'
        filename = 'plano_bancolombia_'+fecha+'.csv'
        file = open(path+filename, "w+")
        #file = open("/opt/odoo15/odoo-server/addons-extra/report_sql/static/"+filename, "w")   
        text_reg_1 = ''
        active_ids = self.env.context.get('active_ids')
        num_reg = len(active_ids)
        total = 0
        count = 0
        journal_id = self.journal_id.id
        company_id = self.journal_id.company_id.partner_id
        tipo_cta = self.journal_id.bank_account_id.tipo_cta
        parameter_bank = self.journal_id.bank_id.bank_parameter_ids
        cuenta_debitar = self.journal_id.bank_account_id.acc_number

        for record in self.env['account.payment'].browse(active_ids):
            if record:
                total += record.amount
                count += 2

        t_c = ''

        if tipo_cta == 'C':
            tipo_cta = 'D'
        elif tipo_cta == 'A':
            tipo_cta = 'S'

        for param in parameter_bank:
            if param.name == tipo_cta:
                t_c =  param.value
                 
        fecha_pago = str(self.date_payment.strftime('%g%m%d'))
        fecha_apli = str(self.date_application.strftime('%g%m%d'))
        nit = str(company_id.vat)
        nit = nit.replace('-','')
        name_company = company_id.name
        num_reg = str(num_reg)
        total = int(total)
        total = str(total)
        
        
        text_reg_1 = '1' + nit.zfill(10) + name_company.ljust (16," ") + self.transaccion + self.descripcion.ljust(10, " ") + fecha_pago + self.sequence + fecha_apli + str(count).zfill(6) + (12 * '0') + total.zfill(12) + str(cuenta_debitar).zfill(11) + str(tipo_cta)
        #text_reg_1 = '1' + nit.zfill(15) + 'I' + (15 * ' ') + self.transaccion + self.descripcion.ljust(10, " ") + fecha_pago + self.lote + self.transaccion + fecha_apli + num_reg.zfill(6) + (17 * ' ') + total.zfill(17) + '0' + str(cuenta_debitar) + t_c
        #text_reg_1 = '1' + company_id.ref.zfill(15) + 'I' + (15 * ' ') + self.transaccion + self.descripcion.ljust(10, " ") + fecha_pago + self.lote + self.transaccion + fecha_apli + num_reg.zfill(6) + (17 * ' ') + total.zfill(17) + '0' + cuenta_debitar + t_c
        
        file.write(text_reg_1 + '\n')     


        # GENERA REGISTROS TIPO 6
        text_reg_2 = ''

        for record in self.env['account.payment'].browse(active_ids):
            if record:
                fecha_pago_2 = str(self.date_payment)
                fecha_pago_2 = fecha_pago_2.replace('-', '')
                fecha_apli_2 = str(self.date_application)
                fecha_apli_2 = fecha_apli_2.replace('-', '')  
                name_partner = str(record.partner_id.name)
                id_partner = str(record.partner_id.vat)
                cod_bank = record.partner_bank_id.bank_id.bic
                cta_partner = str(record.partner_bank_id.acc_number)
                parameter_bank_partner = self.journal_id.bank_id.bank_parameter_ids
                tipo_cta_partner = record.partner_bank_id.tipo_cta
                valor = record.amount
                transaccion = ' '
                if tipo_cta_partner == 'C':
                    transaccion = '27'
                elif tipo_cta_partner == 'A':
                    transaccion = '37'
                t_t = ' '       
                for param in parameter_bank_partner:
                    if param.name == transaccion:
                        t_t =  param.value
                
                valor = int(valor)
                valor = str(valor)
                cod_bank = str(cod_bank)

                print('tipos..........',record.name,record.ref)

                text_reg_2 = '6' + id_partner.rjust(15,'0') + name_partner[0:18] + cod_bank.rjust(9,'0') + cta_partner.ljust(17, "0") + 'S' + transaccion + valor.zfill(10) + record.name[0:9] + str(record.ref[0:9]) + ' '  
                #text_reg_2 = '6' + id_partner.ljust(15, " ") + name_partner.ljust(30, " ") + (5 * '0') + '1' + cod_bank + cta_partner.ljust(17, " ") + ' ' + t_t + valor.zfill(16)+ '0' + fecha_pago_2 + (21 * ' ')
                #file.write(text_reg_2 + '\n')
                file.write(f'{text_reg_2}\n')

        for rec in self.env['account.payment'].browse(active_ids):
            if rec:
                mail = str(record.partner_id.email)
                text_reg_3 = '3@' +  (52 * '*') + mail.ljust(41,' ')
                file.write(f'{text_reg_3}\n')      
        
        file.close()
          
        #print('file .-.-.-.-.-.-.-.-.',file)
        #sudo().os.chmod((path+filename), S_IREAD|S_IRGRP|S_IROTH)
        
        domain = self.env['ir.config_parameter'].get_param("repo.base.url")
        if not domain:
           raise ValidationError('Falta configurar el parámetro del sistema con clave repo.base.url')

        #if not os.path.isdir(domain):
        #   raise ValidationError('El directorio no existe: %s' % (home_report))

        url = domain + filename

        return {
            'name': 'Generar archivo plano',
            'type' : 'ir.actions.act_url',
            'url': url,
            'target': 'self'
            }    
        
        
    def open_wizard(self):
        return {
            'name': 'Generar Archivo Banco',
            'type': 'ir.actions.act_window',
            'res_model': 'payment.export.wizard',
            'target': 'new',
            'views': [(self.env.ref('generate_bank_file.generate_bank_file_wizard_view').id, 'form')],
            'context': {'active_ids': self.env.context.get('active_ids')},
            }


            