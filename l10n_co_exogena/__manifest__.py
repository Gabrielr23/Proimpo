# -*- coding: utf-8 -*-
{
    'name': 'Información Exógena DIAN (Colombia)',
    'version': '18.0.1.3.0',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Genera los formatos de información exógena (medios magnéticos) '
               'de la DIAN a partir de la contabilidad de Odoo.',
    'description': """
Información Exógena DIAN
=======================
Replica la lógica de configuración de formatos y conceptos (como el módulo de
medios magnéticos de CGUNO): se crean los formatos (1001, 1007, 1008, 1009...),
sus conceptos DIAN, y a cada concepto se le asocian las cuentas contables del
PUC. El generador recorre los apuntes contables validados, agrupa por tercero y
concepto, aplica el umbral de cuantías menores y exporta el Excel para el
prevalidador de la DIAN.

Basado en la Resolución 000227 de 2025 (Resolución Única) y sus modificaciones.
""",
    'author': 'PROIMPO SAS',
    'website': 'https://proimpo.odoo.com',
    'license': 'LGPL-3',
    'depends': ['account', 'l10n_co'],
    'data': [
        'security/ir.model.access.csv',
        'views/exogena_formato_views.xml',
        'views/exogena_concepto_views.xml',
        'views/exogena_reporte_views.xml',
        'views/exogena_menus.xml',
        'data/exogena_1001_data.xml',
        'data/exogena_1007_data.xml',
        'data/exogena_1008_data.xml',
        'data/exogena_1009_data.xml',
    ],
    'installable': True,
    'application': True,
}
