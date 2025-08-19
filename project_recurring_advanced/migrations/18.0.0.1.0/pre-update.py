from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['project.task'].search([
        ('parent_id','!=',False),
        ('recurring_task','=',True),
    ]).parent_id = False