{
    'name': 'MRP - Fechas manuales de órdenes de trabajo',
    'version': '18.0.1.0.0',
    'summary': 'Al editar a mano las fechas de una orden de trabajo, respeta la fecha '
               'y no infla la duración (corrige efecto del fix Odoo 115f9f640).',
    'description': """
Desde el commit oficial 115f9f640 ("[FIX] mrp: consider maintenance in gantt planning",
integrado en 18.0 el 30-09-2026), la fecha fin de una orden de trabajo se calcula
saltando las reservas de OTRAS órdenes del mismo centro de trabajo, mientras que la
duración se sigue calculando sin considerarlas. Las dos fórmulas se alimentan entre sí
y la duración crece en cada edición manual.

Este módulo deja ambos cálculos con la misma regla:
- Respeta la fecha que pone el planeador (puede quedar solapada con otra orden;
  el Gantt lo muestra como conflicto).
- Sigue respetando ausencias y mantenimientos del centro de trabajo.
- El botón Planificar no cambia (usa otro método nativo).
""",
    'author': 'PROIMPO S.A.S.',
    'category': 'Manufacturing/Manufacturing',
    'depends': ['mrp'],
    'data': [],
    'installable': True,
    'license': 'LGPL-3',
}
