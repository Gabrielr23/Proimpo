# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Reporte diario de horas extra por aprobar",
    'summary': "Envia cada manana el reporte de horas extra pendientes de aprobacion",
    'description': "Tarea programada que cada manana busca los registros de asistencia del dia "
                   "anterior con horas extra pendientes de aprobacion y envia por correo una tabla "
                   "resumen con enlace directo a Odoo para aprobar o rechazar.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "19.0.2.0.0",
    'depends': ['hr_attendance', 'hr_att_expected', 'mail'],
    'data': [
        'security/groups.xml',
        'views/asistencia_extras_views.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
    'application': False,
}
