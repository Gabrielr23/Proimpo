from odoo import api, fields, models, tools, _


class ResBankParameter(models.Model):
    _name = 'res.bank.parameter.value'
    _description = 'Parametros bancos'
    _order = 'name'

    bank_id = fields.Many2one('res.bank', 'Banco', required=True, store=True, ondelete='cascade')
    name = fields.Char('Atributo', required=True)
    # MIGRACION 19.0 (correccion): el default era 'Numerico', que NO es un
    # valor valido de la seleccion [('N','Numerico'),('A','Alfanumerico')].
    # Al ser required, Odoo dejaba el campo vacio en cada registro nuevo.
    data_type = fields.Selection(string='Tipo de Campo', required=True, selection=[('N', 'Numerico'), ('A', 'Alfanumerico')], default='N')
    # MIGRACION 19.0: se elimina el parametro 'size'. Solo fields.Char lo
    # acepta; en un Integer Odoo 19 lo reporta en el log como
    # "Field res.bank.parameter.value.size: unknown parameter 'size'".
    size = fields.Integer(string='Tamano', default=1)
    value = fields.Char(string='Valor', size=10)

    # MIGRACION 19.0: _sql_constraints ya no es soportado
    # (odoo/orm/model_classes.py emite el WARNING "Model attribute
    # '_sql_constraints' is no longer supported, please define
    # models.Constraint on the model" y la restriccion NO se crea).
    _bank_id_name_uniq = models.Constraint(
        'unique (bank_id, name)',
        "No puede tener dos parametros con el mismo nombre para el mismo banco",
    )


class ResBank(models.Model):
    _inherit = 'res.bank'

    bank_parameter_ids = fields.One2many('res.bank.parameter.value', 'bank_id', 'Parametros para el banco')


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    tipo_cta = fields.Selection(string='Tipo de Cuenta', required=True, selection=[('C', 'Corriente'), ('A', 'Ahorro'), ('R', 'Rotativo')], default='C')
