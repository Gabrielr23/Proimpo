# -*- coding: utf-8 -*-
{
    'name': 'Gestión de Moldes de Inyección',
    'version': '18.0.1.2.0',
    'summary': 'Moldes como equipos de mantenimiento: cavidades, ciclo, centros '
               'compatibles, LdM calificadas y objetivo de producción por hora.',
    'description': """
Gestión de Moldes de Inyección
===============================

Modela el molde como una extensión de `maintenance.equipment`, para heredar
de forma nativa: calendario de mantenimiento preventivo, solicitudes
correctivas, técnico asignado y categorías — sin reconstruir ese sistema
en paralelo.

Añade lo específico de producción:

* Cavidades actuales, ciclo teórico y ciclo actual (cambian por desgaste)
* Centros de trabajo compatibles (sin orden estricto: el planeador decide)
* LdM para las que el molde está calificado
* Objetivo de producción por hora, calculado en vivo desde ciclo y cavidades
* Bitácora de revisión de molde (misma estructura que el control manual
  existente: fecha, análisis, acción, responsable, fecha de ejecución,
  cumple, observaciones), con botón para aplicar los valores verificados
  al molde

En la Orden de Trabajo: selección de molde (filtrada por centro de trabajo
compatible) y visualización del objetivo por hora resultante.

No incluye todavía: validación de choque de horario entre órdenes que
reclaman el mismo molde. Queda para una siguiente iteración.
""",
    'author': 'PROIMPO S.A.S.',
    'category': 'Manufacturing',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'maintenance',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/maintenance_equipment_views.xml',
        'views/mrp_workorder_views.xml',
        'views/mold_revision_log_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
