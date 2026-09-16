# -*- coding: utf-8 -*-
{
    'name': 'Resolución de Turnos de Producción',
    'version': '18.0.1.1.0',
    'summary': 'Determina a qué turno de producción pertenece una fecha/hora, '
               'según el calendario del centro de trabajo.',
    'description': """
Resolución de Turnos de Producción
====================================

Fase A del proyecto de OEE/tablero de piso. Sin vistas ni modelos nuevos
visibles — es lógica de apoyo para los módulos que vienen después
(mrp_oee_report, mrp_oee_dashboard, mrp_production_alerts).

Regla de identificación de turno (confirmada con datos reales de la
instancia): el NOMBRE de la línea de asistencia del calendario
("Lunes Turno 3") es la única fuente de verdad. `day_period` (morning/
lunch/afternoon) se usa exclusivamente para saber si esa franja tiene
capacidad planeada (`lunch` = objetivo 0), nunca para identificar el turno
en sí ni para decidir si la producción real se descarta.

El cruce de medianoche no requiere lógica especial: Odoo ya parte un turno
que cruza la medianoche en dos líneas de asistencia (una por cada
`dayofweek`), y ambas comparten el mismo nombre. Basta con buscar por
día real de la semana + hora real, sin comparar contra "hoy".

Soporta calendarios versionados (`date_from`/`date_to` en las líneas de
asistencia): cada resolución usa la versión vigente en la fecha analizada,
así que un cambio futuro de horarios no distorsiona los reportes históricos.
""",
    'author': 'PROIMPO S.A.S.',
    'category': 'Manufacturing',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'resource',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
