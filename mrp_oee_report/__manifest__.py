# -*- coding: utf-8 -*-
{
    'name': 'Informe de OEE por Turno',
    'version': '18.0.1.0.0',
    'summary': 'Disponibilidad, Rendimiento, Calidad y OEE por máquina, '
               'fecha operativa y turno.',
    'description': """
Informe de OEE por Turno
=========================

Fase B del proyecto de OEE/tablero de piso. Vista SQL de solo lectura,
con grano: centro de trabajo x fecha operativa x turno.

A diferencia de mrp_averias_report (que ancla solo en horas CON avería y
por eso tiene un universo sesgado), este informe ancla en TODAS las líneas
de mrp.workcenter.productivity, por lo que sus denominadores son reales.

Fórmulas:
  Disponibilidad = minutos productivos / minutos totales
  Rendimiento    = (buenas + averías) / unidades teóricas
  Calidad        = buenas / (buenas + averías)
  OEE            = Disponibilidad x Rendimiento x Calidad

Objetivo por hora de cada línea, con cadena de respaldo:
  1. Molde de la orden/operación: 3600 / (ciclo efectivo / cavidades)
  2. Ciclo manual de la operación: 60 / time_cycle_manual

Las unidades teóricas solo se acumulan en tiempo PRODUCTIVO y en turno
PLANEADO. En una franja de capacidad apagada (day_period 'lunch') el
objetivo es 0 por diseño: la producción real se reporta igual, pero sin
porcentaje de Rendimiento ni OEE (turno extra / no planeado).

Semáforo: verde >= 80%, amarillo 70-80%, rojo < 70%.
""",
    'author': 'PROIMPO S.A.S.',
    'category': 'Manufacturing',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'mrp_shift_resolver',
        'mrp_mold_management',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_oee_report_views.xml',
        'data/menu_placement.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
