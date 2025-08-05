from odoo import models, fields, api, exceptions, tools, _

class ProjectTaskRecurrence(models.Model):
    _inherit = 'project.task.recurrence'

    @api.model
    def _get_recurring_fields_to_copy(self):
        return [
            'repeat_user_ids',
            'repeat_stage_id',
            'repeat_deadline',
            'repeat_deadline_count',
            'repeat_deadline_unit',
            'repeat_name'
        ] + super(ProjectTaskRecurrence, self)._get_recurring_fields_to_copy()

    def _create_next_occurrence_values(self, occurrence_from):
        create_values = super(ProjectTaskRecurrence, self)._create_next_occurrence_values(occurrence_from)
        if occurrence_from.repeat_user_ids:
            create_values['user_ids'] = [(6, 0, occurrence_from.repeat_user_ids.ids)]
        if occurrence_from.repeat_deadline:
            create_values['date_deadline'] = occurrence_from._calculate_date_deadline()
        if occurrence_from.repeat_stage_id:
            create_values['stage_id'] = occurrence_from.repeat_stage_id.id
        return create_values

    