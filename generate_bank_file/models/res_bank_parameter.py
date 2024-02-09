from odoo import api, fields, models, tools, _


class ResBankParameter(models.Model):
    _name = 'res.bank.parameter.value'
    _description='Parametros bancos'
    _order = 'name'
    
    
    bank_id = fields.Many2one('res.bank', 'Banco', requires=True, store=True, ondelete='cascade')
    name = fields.Char('Atributo', required=True)
    data_type = fields.Selection(string='Tipo de Campo', requires=True, selection=[('N','Numerico'),('A','Alfanumerico')], default='Numerico')
    size = fields.Integer(string='Tamaño',size=3, default=1)
    value = fields.Char(string='Valor', size=10)
    


    _sql_constraints = [
        ('_unique', 'unique (rule_parameter_id, name)', "No puede tener dos parametros con el mismo nombre"),
    ]

class ResBank(models.Model):
    _inherit = 'res.bank'

    bank_parameter_ids = fields.One2many('res.bank.parameter.value', 'bank_id', 'Parametros para el banco')   


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    tipo_cta = fields.Selection(string='Tipo de Cuenta', requires=True, selection=[('C','Corriente'),('A','Ahorro'),('R','Rotativo')], default='C')


    