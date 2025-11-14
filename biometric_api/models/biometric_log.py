from odoo import models, fields

class BiometricLog(models.Model):
    _name = 'biometric.log'
    _description = 'Log de datos recibidos del Biométrico'
    _order = 'create_date desc'

    payload = fields.Json(string="Payload")
    create_date = fields.Datetime(string="Fecha de recepción", readonly=True)
