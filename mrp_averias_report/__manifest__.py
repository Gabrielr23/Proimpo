# -*- coding: utf-8 -*-
{
    'name': 'Informe de Averías Tipificadas',
    'version': '18.0.1.1.0',
    'summary': 'Consolida las tipificaciones de averías registradas en las hojas '
               'de trabajo de calidad y las expone como informe (pivot/gráfico/lista).',
    'description': """
Informe de Averías Tipificadas
==============================

Crea un modelo de solo lectura (vista SQL) que une las líneas de tipificación
de TODAS las plantillas de hoja de trabajo de calidad y las cruza con:

* Control de calidad, punto de control y estado
* Orden de fabricación y orden de trabajo
* Centro de trabajo y operación (proceso)
* Producto y categoría de producto
* Fecha real del turno (línea de seguimiento de tiempo)

No duplica datos: lee directamente de las tablas generadas por Studio.
Los nombres de esas tablas se descubren dinámicamente, por lo que el módulo
no depende de sufijos aleatorios.

Requisitos en las líneas de la hoja de trabajo:
  - x_studio_turno              (selection)
  - x_studio_averias            (selection)
  - x_studio_cantidad_averias   (integer)
""",
    'author': 'PROIMPO S.A.S.',
    'category': 'Manufacturing/Quality',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'hr',
        'quality_control',
        'quality_mrp',
        'quality_control_worksheet',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_averia_report_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
