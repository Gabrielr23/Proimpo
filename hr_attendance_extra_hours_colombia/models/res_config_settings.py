# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    attendance_nocturnal_start = fields.Float(
        string="Inicio Horario Nocturno",
        config_parameter='attendance.nocturnal_start',
        default=21.0,
        help="Hora de inicio del horario nocturno (formato 24h, ej: 21.0 = 9:00 PM)"
    )

    attendance_nocturnal_end = fields.Float(
        string="Fin Horario Nocturno",
        config_parameter='attendance.nocturnal_end',
        default=6.0,
        help="Hora de fin del horario nocturno (formato 24h, ej: 6.0 = 6:00 AM)"
    )

    attendance_extra_rounding = fields.Integer(
        string="Redondeo de Horas Extras (minutos)",
        config_parameter='attendance.extra_rounding',
        default=15,
        help="Las horas extras se redondearán a este intervalo en minutos (ej: 15 = cuartos de hora)"
    )

    @api.constrains('attendance_nocturnal_start', 'attendance_nocturnal_end')
    def _check_nocturnal_hours(self):
        for record in self:
            if record.attendance_nocturnal_start < 0 or record.attendance_nocturnal_start > 24:
                raise models.ValidationError("La hora de inicio nocturno debe estar entre 0 y 24")
            if record.attendance_nocturnal_end < 0 or record.attendance_nocturnal_end > 24:
                raise models.ValidationError("La hora de fin nocturno debe estar entre 0 y 24")

    @api.constrains('attendance_extra_rounding')
    def _check_rounding(self):
        for record in self:
            if record.attendance_extra_rounding <= 0 or record.attendance_extra_rounding > 60:
                raise models.ValidationError("El redondeo debe estar entre 1 y 60 minutos")
