# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Ocultar botones DIAN de Jorels no usados",
    'summary': "Deja invisibles los botones y pestañas de nómina/facturación "
               "electrónica de Jorels que PROIMPO no usa (usa su propia solución), "
               "sin desinstalar ni alterar el motor.",
    'description': "Módulo cosmético: hereda las vistas de recibo de nómina y de "
                   "facturas para ocultar los botones DIAN de Jorels (Validate DIAN, "
                   "Consult DIAN, Test de validación, previsualizaciones) y las "
                   "pestañas Edi Response / Edi Payload. No toca lógica ni datos; "
                   "se puede desinstalar para revertir.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "19.0.1.0.0",
    'depends': [
        'l10n_co_hr_payroll_enterprise',
        'l10n_co_edi_jorels',
    ],
    'data': [
        'views/ocultar_jorels_ui.xml',
    ],
    'installable': True,
    'application': False,
}
