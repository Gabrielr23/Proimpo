# -*- coding: utf-8 -*-
{
    'name': 'PROIMPO Nómina - Cargue masivo de novedades',
    'version': '19.0.1.1.0',
    'summary': 'Sube un Excel de novedades (horas extra, comisiones, bonificaciones) a un lote de nómina',
    'description': """
Asistente para cargar novedades de forma masiva a un lote de nómina.

- Horas extra/recargos (HED, HEN, HRN, HEDDF, HRDDF, HENDF, HRNDF): se digitan en
  HORAS; el sistema calcula el valor con el salario del empleado (divisor 220 hasta
  2026-07-14 y 210 desde 2026-07-15) y el factor de recargo.
- Comisiones (COM), Bonificación salarial (BON), Bonificación no salarial (BONNS):
  se digitan en VALOR (pesos).

Crea las líneas de devengado (earn.line) en cada recibo del lote emparejando por
cédula (o nombre) y recalcula. Útil para pruebas (p. ej. límite del 40%, Ley 1393)
y para el registro de novedades en producción.
""",
    'author': 'Proimpo SAS',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/cargar_novedades_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
