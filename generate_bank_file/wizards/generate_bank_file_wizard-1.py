# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, RedirectWarning
from odoo.tools.misc import formatLang, format_date


class PaymentExportWizard(models.TransientModel):
    
    _name = "payment.export.wizard"
    _description = "Genera plano bancos Colombia"

   
    date_payment = fields.Date(string="Fecha Pago", required=True, default=fields.Date.context_today)
    date_application = fields.Date(string="Fecha aplicacion", required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(string="Diario", 'account.journal', required=True, domain="[('company_id', '=', company_id), ('type', 'in', ['bank'])]")
    transaccion = fields.Selection(string='Tipo de Transaccion', requires=True, selection=[('220','220 - Pago a Proveedores'),
                                                                                           ('221','221 - Pago a Proveedores'),
                                                                                           ('225','225 - Pago de Nomina'),
                                                                                           ('226','226 - Pago de Nomina'),
                                                                                           ('238','238 - Pago Terceros')], default='220 - Pago a Proveedores')
    descripcion = fields.Char(string='Descripcion', size=10)
    lote = fields.Char(string='Lote', size=2, help='No puede enviarse la misma secuencia un mismo dia Ej. A1,A2...', placeholder="A1,A2....." )                                                                                     

    def create_file(self, order, lines):
        self.num_records = 0
        if self.order.mode.type.code == 'conf_popular':
            txt_file = self._pop_cabecera()
            for line in lines:
                txt_file += self._pop_beneficiarios(line)
                txt_file += self._pop_detalle(line)
            txt_file += self._pop_totales(line, self.num_records)
        return txt_file 

    def export_txt(self):

    #def _reg_1(self):    
        text_reg_1 = ''
        active_ids = self.env.context.get('active_ids')
        num_reg = len(active_ids)
        total = 0
        journal_id = self.journal_id.id
        company_id = self.journal_id.company_id.partner_id
        tipo_cta = self.journal_id.bank_account_id.tipo_cuenta
        parameter_bank = self.journal_id.bank_id.bank_parameter_ids
        cuenta_debitar = self.journal_id.bank_account_id.acc_number
        for record in self.env['account.payment'].browse(active_ids):
            if record:
                total += record.amount
        t_c = ''
        print('parameter_bank.-.-.-.-.-.-.-.-.-.-.-.',parameter_bank)
        for param in parameter_bank:
            print('param.-.-.-.-.-.-.-.-.-.-.-.',param)
            if tipo_cta == parameter.name:
                t_c = parameter.value


        fecha_pago = self.date_payment
        fecha_pago = fecha_pago.replace('-', '')
        fecha_apli = self.date_application
        fecha_apli = fecha_apli.replace('-', '')
        #dia = fecha_pago[6:]
        #mes = fecha_pago[4:6]
        #ano = fecha_pago[:4]
        #fecha_pago = dia + mes + ano

        text_reg_1 += '1' + company_id.ref.zfill(15) + 'I' + (15 * ' ') + self.transaccion + self.descripcion + 
                      fecha_pago + self.transaccion + fecha_apli + num_reg.zfill(6) + (17 * ' ') + total.zfill(17) + cuenta_debitar + t_c
              



        print('taxt_reg -.-.-.-.-.-.-.-.-.-.', text_reg)  
                


        #print('record -.-.-.-.-.-.-.-.-.-.-.-.', record.name,'cantidad de pagos',num_records,'Total = ',total,'journal_id --', journal_id,'Company_id--',company_id.ref.zfill(15))


    
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


            