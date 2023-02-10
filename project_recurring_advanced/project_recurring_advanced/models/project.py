from odoo import models, fields, api, exceptions, tools, _
from dateutil.relativedelta import relativedelta

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
        return fields.Date.context_today(self) + relativedelta(**{self.repeat_deadline_unit: self.repeat_deadline_count})