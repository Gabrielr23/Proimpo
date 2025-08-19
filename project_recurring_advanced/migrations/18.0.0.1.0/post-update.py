from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.ref('project_recurring_advanced.view_project_task_form_inherit', raise_if_not_found=False).active = True

