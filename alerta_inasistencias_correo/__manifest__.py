# -*- coding: utf-8 -*-
{
    'name': 'Alerta de Inasistencias por Correo a RH',
    # Verificado contra el código fuente de Odoo 19.0 (rama 19.0 de
    # github.com/odoo/odoo, 2026-11-04): mail.mail.email_cc existe, hr.leave
    # state 'validate' existe, hr_attendance.menu_hr_attendance_root y
    # hr_attendance.group_hr_attendance_manager existen, y los campos de
    # hr.employee usados (identification_id, private_country_id,
    # private_state_id, address_id, resource_calendar_id) siguen accesibles
    # desde el empleado (en 19.0 viven en hr.version vía _inherits).
    'version': '19.0.1.1.0',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'summary': (
        'Envía por correo a RH el reporte de inasistencias, 3 veces al día '
        '(alineado con turnos.md) más un resumen diario, con Excel adjunto. '
        'Incluye un botón para enviarlo también de forma manual/instantánea.'
    ),
    'description': """
Alerta de Inasistencias por Correo a RH
========================================

Módulo liviano (sin modelos de datos nuevos, sin tablas que crezcan) que:

- Agrega un método a hr.attendance (el módulo/app al que pertenece
  naturalmente este reporte) que genera el reporte de inasistencias,
  reutilizando la misma lógica de clasificación de
  "inasistencias_hoy (V4).py", exporta el Excel completo como adjunto, y
  envía el correo a RH (con copia de respaldo) — ver
  PLAN_Modulo_Alerta_Correo_RH.md para el detalle de cada decisión.
- Agrega un asistente (wizard) con un botón "Enviar alerta ahora" para
  disparar el envío manualmente en cualquier momento, además de los 4
  ir.cron programados (que se configuran aparte, ver el modo de uso al
  final de models/hr_attendance.py). El botón y el envío están
  restringidos a los administradores de Asistencias.

Por qué es un módulo instalable (y no solo una Acción de Servidor con el
código pegado): el reporte usa una librería externa (xlsxwriter) y es
demasiado extenso para el sandbox restringido en el que corre el código de
una Acción de Servidor. Empaquetado como método de un modelo, corre como
Python normal sin esa restricción; la Acción de Servidor / el botón del
wizard solo necesitan una línea que lo invoque.
""",
    'author': 'Proimpo S.A.S',
    'depends': [
        'base',
        'hr',
        'hr_attendance',
        'hr_holidays',
        'resource',
        'mail',
    ],
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/alerta_inasistencias_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
