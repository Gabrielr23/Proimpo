{
    'name': 'Fix: acceso a ausencias en Gantt (horario flexible)',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Evita AccessError en los Gantt de Asistencias y Planificación '
               'para usuarios sin permisos de Ausencias (regresión Odoo 8227bbbe1410)',
    'description': """
Parche temporal para la regresión introducida por Odoo en el commit 8227bbbe1410
(PR odoo/odoo#261597, opw-6142094) del 15-09-2026.

hr_holidays/models/resource.py -> ResourceCalendar._get_flexible_leaves_date
lee holiday_id.request_unit_half / request_unit_hours sin sudo(), lo que
provoca un AccessError al abrir los Gantt de Asistencias y Planificación
cuando el usuario no tiene permisos de Ausencias y hay empleados con horario
flexible con ausencias en el rango visible.

Este módulo entrega los registros de ausencias con sudo() únicamente para el
cálculo de fechas de indisponibilidad. No expone información de las ausencias
al usuario.

Desinstalar cuando Odoo publique la corrección oficial.
    """,
    'author': 'PROIMPO S.A.S',
    'depends': ['hr_holidays'],
    'data': [],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
