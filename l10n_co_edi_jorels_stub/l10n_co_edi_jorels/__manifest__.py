# -*- coding: utf-8 -*-
# l10n_co_edi_jorels — Stub para Nómina Electrónica DIAN
#
# Versión recortada de l10n_co_edi_jorels de Jorels SAS.
# Incluye ÚNICAMENTE los modelos de catálogos y configuración de empresa
# necesarios para el módulo l10n_co_hr_payroll (nómina electrónica DIAN).
#
# NO modifica facturas, notas crédito, Carvajal, ni ningún módulo de
# facturación electrónica existente.
#
# Los datos se cargan vía init_csv_data (SQL directo) del módulo update_from_csv,
# igual que el módulo original de Jorels — sin xmlids, sin conflictos.
#
# Licencia original: LGPL-3 (Jorels SAS - info@jorels.com)

{
    'name': "l10n_co_edi_jorels (Stub Nómina DIAN)",
    'summary': 'Catálogos DIAN y configuración para Nómina Electrónica — sin modificar facturación',
    'description': """
Versión recortada de l10n_co_edi_jorels para uso exclusivo con nómina electrónica.
No toca account.move, account.move.send, res.partner ni ninguna vista de facturas.
Provee los catálogos DIAN y los campos de empresa requeridos por l10n_co_hr_payroll.

Los catálogos se cargan mediante init_csv_data (INSERT ... ON CONFLICT) del módulo
update_from_csv, evitando conflictos de xmlids con otros módulos instalados.
    """,
    'author': "Jorels SAS / Adaptado para compatibilidad con Carvajal",
    'license': "LGPL-3",
    'category': 'Payroll',
    'version': '18.0.24.05.010000',
    'depends': [
        'account',
        'l10n_co',
        'update_from_csv',
        'base_vat',
    ],
    'data': [
        'security/ir.model.access.csv',
        # Catálogos DIAN via init_csv_data (SQL directo — sin conflicto de xmlids)
        'data/data.xml',
        # Vistas — solo pestaña de nómina en empresa
        'views/config/res_company_payroll.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
