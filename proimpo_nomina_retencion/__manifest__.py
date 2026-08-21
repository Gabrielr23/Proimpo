# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Retención en la fuente (Proc. 1)",
    'summary': "Depuración de retención procedimiento 1 con proyección 1Q/ajuste 2Q y reporte de auditoría",
    'description': """
Calcula la retención en la fuente por el Procedimiento 1, replicando la
depuración del reporte de auditoría de CGUNO (6 secciones):
 1. Ingresos brutos
 2. Ingresos no constitutivos de renta (salud, pensión, FSP obligatorios)
 3. Deducciones Art. 387 (dependientes, medicina prepagada, intereses de vivienda)
 4. Rentas exentas (AFC / pensión voluntaria + 25% exento)
 5. Excedente (límite del 40%, Art. 336)
 6. Retención (tabla Art. 383 en UVT)
En la primera quincena proyecta (salario + variables x2) y retiene el total;
en la segunda quincena recalcula con el real del mes y ajusta (retiene o devuelve).
Incluye un reporte PDF de auditoría por recibo.
    """,
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': '18.0.1.5.3',
    'depends': ['l10n_co_hr_payroll_enterprise'],
    'data': [
        'report/rtf_report.xml',
        'views/hr_payslip_views.xml',
    ],
    'installable': True,
    'application': False,
}
