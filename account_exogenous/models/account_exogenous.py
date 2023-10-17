# -*- encoding: utf-8 -*-

from odoo import api, fields, models, tools, _


class account_activity_economic(models.Model):
    _name = "account.activity.economic"
    _description = "Actividad economica"
        
    code = fields.Char('Codigo', required=True,size=4)
    name = fields.Char('Actividad', required=True,size=100)
    
 
class res_partner(models.Model):
    _inherit = 'res.partner'
                  
    activity_economic_id = fields.Many2one('account.activity.economic', required=True, string='Actividad economica')
       
    

class account_formato_dian(models.Model):
    _name = "account.formato.dian"
    _description = "Formatos DIAN"
        
    
    code = fields.Char('Codigo', required=True,size=4)
    name = fields.Char('Formato', required=True,size=150)
    version = fields.Integer('Version', required=True)
    ejemplo = fields.Text('Ejemplo XML')
    explicacion = fields.Text('Explicacion')
    campos_ids = fields.One2many('account.campos.formato', 'formato_id', 'Campos', copy=True)
    

    _sql_constraints = [('version_uniq', 'unique(code, version)', 'Ya existe la version para el mismo formato')]

class account_campos_formato(models.Model):
    _name = "account.campos.formato"
    _description = "Campos del formato"
    
    name = fields.Char('Nombre', required=True,size=150)
    referencia = fields.Char('Referencia', required=False ,size=50)
    formato_id = fields.Many2one('account.formato.dian', 'Formato', required=True, index=True)
    tipo_id = fields.Many2one('account.tipos.campo', 'Tipo de campo', required=True, index=True)
    tipo_valor_id = fields.Many2one('account.tipos.valor',  string='Tipo de valor')
    sequence = fields.Integer('Secuencia', required=True, index=True)
    conceptos_ids = fields.One2many('account.conceptos.conceptos.rel', 'campo_id', 'Conceptos relacionados', copy=True)
    
    
    _sql_constraints = [('sequence_uniq', 'unique(formato_id, sequence)', 'Ya existe la secuencia para este formato')]
    
    _order = 'formato_id, sequence'
    _defaults = {
         'sequence': 10,
    }

class account_conceptos(models.Model):
    _name = "account.conceptos"
    _description = "Conceptos"
        
    code = fields.Char('Codigo', required=True,size=15)
    name = fields.Char('Nombre', required=True,size=214)
    porcentaje_no_deducible = fields.Char('Porcentaje no deducible',size=2)
    tope = fields.Float('Topen', help = "Tope base del concepto")
    form_dian_id = fields.Many2one('account.formato.dian', required=True, string='Formato DIAN')
    cuentas_ids = fields.One2many('account.conceptos.rel', 'concepto_id', 'Cuentas', copy=True)
    
    
    _sql_constraints = [('uniq', 'unique(code)', 'El codigo ya existe')]


class account_conceptos_conceptos_rel(models.Model):
    _name = 'account.conceptos.conceptos.rel'
    _description = 'Relacion de Conceptos Conceptos'
                     
    campo_id = fields.Many2one('account.campos.formato',  string='Campo formato')
    concepto_id = fields.Many2one('account.conceptos',  string='Concepto formato')
    concepto_rel_id = fields.Many2one('account.conceptos',  string='Concepto relacionado')
    
    
    _sql_constraints = [('uniq', 'unique(campo_id, concepto_id, concepto_rel_id)', 'Ya existe la relacion de conceptos para esta columna')]



class account_conceptos_rel(models.Model):
    _name = "account.conceptos.rel"
    _description = "Relacion Conceptos"
       
    concepto_id = fields.Many2one('account.conceptos', required=True,  string='Conceptos')
    cuenta_id = fields.Many2one('account.account', string='Cuenta', required=True, domain="[('internal_type','!=','view')]")
    
    
    _sql_constraints = [('cuenta_uniq', 'unique(concepto_id, cuenta_id)', 'Ya existe la cuenta para este concepto')]


class account_tipos_campos(models.Model):
    _name = "account.tipos.campo"
    _description = "Tipos de campo"
    
    code = fields.Char('Codigo', required=True,size=50)
    name = fields.Char('Nombre', required=True,size=214)
    
    
    _sql_constraints = [('uniq', 'unique(code)', 'El codigo ya existe')]


class account_tipos_valor(models.Model):
    _name = "account.tipos.valor"
    _description = "Tipos de valor"
        
    code = fields.Char('Codigo', required=True,size=30)
    name = fields.Char('Nombre', required=True,size=150)
    
    
    _sql_constraints = [('uniq', 'unique(code)', 'El codigo ya existe')]


class account_condiciones_especiales(models.Model):
    _name = "account.condiciones.especiales"
    _description = "Condiciones esp. del trabajador"
        
    code = fields.Char('Codigo', required=True,size=4)
    name = fields.Char('Nombre', required=True,size=150)
    


class account_tipos_de_vinculacion(models.Model):
    _name = "account.tipos_de_vinculacion"
    _description = "Tipos de vinculacion"
        
    code = fields.Char('Codigo', required=True,size=4)
    name = fields.Char('Nombre', required=True,size=150)

class res_country(models.Model):
    _inherit = 'res.country'
    
    code_dian = fields.Char('Codigo DIAN', required=True,size=10)      
    

    