# -*- coding: utf-8 -*-
{
    'name': 'Gestión de Moldes de Inyección',
    'version': '18.0.2.3.0',
    'summary': 'Moldes como equipos de mantenimiento: cavidades, ciclo, centros '
               'compatibles, LdM calificadas y objetivo de producción por hora.',
    'description': """
Gestión de Moldes de Inyección
===============================

Modela el molde como una extensión de `maintenance.equipment`, para heredar
de forma nativa el calendario de mantenimiento preventivo, las solicitudes
correctivas, el técnico asignado y las categorías, sin reconstruir ese
sistema en paralelo.

Qué aporta
----------
* Especificaciones: cavidades, ciclo teórico/actual, dimensiones, peso,
  setup y objetivo por hora.
* Situación calculada (esperando compra, disponible, en producción, en
  reparación, dado de baja) separada de la decisión manual de habilitar o
  inhabilitar el molde para producción.
* Ubicación en dos capas: ubicación de almacenamiento fija y ubicación actual derivada de hechos
  (orden de trabajo en curso, solicitud de mantenimiento abierta), con
  override manual y botón "Devolver a su ubicación".
* Moldes alternativos por operación de LdM: el equivalente a los centros
  de trabajo alternativos, pero para moldes.
* Ocupación del molde en el tiempo y detección de conflictos entre órdenes.
* Compra por orden de compra: llegada prevista y fecha real de recepción.
* Alertas: fuera demasiado tiempo, fuera sin solicitud de mantenimiento,
  llegada vencida.
* Informe de días en reparación por taller externo.
* Decisión A: todo producto de la categoría Moldes tiene su molde en
  Mantenimiento; se crea solo al nacer el producto, y un asistente genera
  los de los productos que ya existían.
* Menú único "Moldes" y una sola pantalla de Ocupación de Moldes.

Lo que NO hace, a propósito
---------------------------
Elegir el molde optimizando fecha de entrega, dependencias entre
operaciones y carga de los centros. Eso es un planificador: necesita ver
todas las órdenes a la vez, no una, y pertenece a un módulo aparte. Este
módulo expone las restricciones y la consulta de disponibilidad
(`get_available_molds`) que ese planificador consumiría.
""",
    'author': 'PROIMPO S.A.S.',
    'category': 'Manufacturing',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'maintenance',
        'purchase',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/maintenance_equipment_views.xml',
        'views/mrp_workorder_views.xml',
        'views/mrp_routing_workcenter_views.xml',
        'views/mold_revision_log_views.xml',
        'views/mold_zone_views.xml',
        'views/mold_repair_report_views.xml',
        'views/mold_generate_wizard_views.xml',
        'views/mold_wizards_views.xml',
        'data/cron.xml',
        'data/menu_placement.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
