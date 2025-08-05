from odoo import models, fields, api, exceptions, tools, _
from odoo.tools.safe_eval import safe_eval, time
from dateutil.relativedelta import relativedelta

import logging
_logger = logging.getLogger(__name__)

class ProjectTask(models.Model):

    _inherit = 'project.task'

    repeat_user_ids = fields.Many2many(string="Repeat Assignees", comodel_name="res.users", relation="project_task_repeat_users", column1="task_id", column2="user_id",
        domain="[('share', '=', False), ('active', '=', True)]")
    repeat_stage_id = fields.Many2one('project.task.type', string="Repeat Starting Stage", 
        domain="[('project_ids', '=', project_id)]")
    repeat_deadline = fields.Boolean(string="Repeat Deadline")
    repeat_deadline_count = fields.Integer(
        'Deadline Delay Count', default=0,
        help='Number of days/week/month after task create date. It allows to set a default task deadline.')
    repeat_deadline_unit = fields.Selection([
        ('days', 'days'),
        ('weeks', 'weeks'),
        ('months', 'months')], string="Deadline Delay Units", help="Unit of delay", required=True, default='days')
    repeat_name = fields.Char(string="Repeat Name")

    def _calculate_date_deadline(self):
        return fields.Datetime.now() + relativedelta(**{self.repeat_deadline_unit: self.repeat_deadline_count})

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        for task, vals in zip(self, vals_list):
            if default.get('repeat_name'):
                try:
                    vals['name'] = safe_eval(task.repeat_name, {'object': task, 'time': time, 'today': fields.Date.today()})
                except Exception as e:
                    _logger.error(e)
        return vals_list