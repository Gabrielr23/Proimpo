{
    'name': 'Calidad - Controles Periódicos por Horas',
    'version': '18.0.1.0.0',
    'summary': (
        'Genera controles de calidad con periodicidad en HORAS, '
        'condicionados a que la orden de fabricación esté en curso'
    ),
    'description': """
Motor propio de controles de calidad periódicos por horas
===========================================================

Odoo (18 y 19) solo admite Días, Semanas o Meses como unidad de
"Frecuencia de control" en los Puntos de Control de Calidad
(quality.point). No existe una unidad de horas, y el mecanismo nativo
"Periódicamente" se dispara por eventos de producción, no por un reloj
de fondo — así que ni forzando la unidad se conseguiría un control
generado cada N horas en tiempo real.

Este módulo NO modifica el mecanismo nativo de Calidad. Agrega, de forma
aditiva:

- 3 campos nuevos en quality.point: activar el motor por horas, el
  intervalo en horas, y la fecha del último control generado.
- UNA Acción Programada genérica (no una por cada punto de control) que
  cada 15 minutos revisa todos los puntos de control con el motor
  activo, y si ya se cumplió su intervalo, crea un quality.check por
  cada Orden de Fabricación en estado "En proceso" del producto
  vigilado por ese punto.

Agregar un nuevo control por horas (p. ej. para otro producto
semi-terminado) es exactamente igual de simple que crear cualquier
Punto de Control hoy: no requiere tocar código ni la Acción Programada
    """,
    'category': 'Manufacturing/Quality',
    'author': 'PROIMPO S.A.S.',
    'depends': ['quality_control', 'quality_mrp', 'mrp'],
    'data': [
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
