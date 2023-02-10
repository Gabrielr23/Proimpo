from odoo import models, fields, api, exceptions, tools, _
from odoo.tools.safe_eval import safe_eval, time

import logging
_logger = logging.getLogger(__name__)

class ProjectTaskRecurrence(models.Model):
    _inherit = 'project.task.recurrence'

    @api.model
    def _get_recurring_fields(self):
        return [
            'repeat_user_ids',
            'repeat_stage_id',
            'repeat_deadline',
            'repeat_deadline_count',
            'repeat_deadline_unit',
            'repeat_name'
        ] + super()._get_recurring_fields()

    def _new_task_values(self, task):
        values = super(ProjectTaskRecurrence, self)._new_task_values(task)
        if task.repeat_user_ids:
            values['user_ids'] = [(6, 0, task.repeat_user_ids.ids)]
        if task.repeat_deadline:
            values['date_deadline'] = task._calculate_date_deadline()
        if task.repeat_stage_id:
            values['stage_id'] = task.repeat_stage_id.id
        if task.repeat_name:
            try:
                values['name'] = safe_eval(task.repeat_name, {'object': task, 'time': time, 'today': fields.Date.today()})
            except Exception as e:
                _logger.error(e)

        return values