# -*- coding: utf-8 -*-
# l10n_co_edi_jorels — Stub para Nómina Electrónica DIAN
#
# Este módulo es una versión recortada de l10n_co_edi_jorels de Jorels SAS.
# Incluye ÚNICAMENTE los modelos de catálogos y configuración de empresa
# necesarios para el módulo l10n_co_hr_payroll (nómina electrónica DIAN).
#
# NO modifica facturas, notas crédito, Carvajal, ni ningún módulo de
# facturación electrónica existente.
#
# Licencia original: LGPL-3 (Jorels SAS - info@jorels.com)

{
    'name': "l10n_co_edi_jorels (Stub Nómina DIAN)",
    'summary': 'Catálogos DIAN y configuración para Nómina Electrónica — sin modificar facturación',
    'description': """
Versión recortada de l10n_co_edi_jorels para uso exclusivo con nómina electrónica.
No toca account.move, account.move.send, res.partner ni ninguna vista de facturas.
Provee los catálogos DIAN y los campos de empresa requeridos por l10n_co_hr_payroll.
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
        # Catálogos — orden importa (languages primero, postal al final)
        'data/l10n_co_edi_jorels.languages.csv',
        'data/l10n_co_edi_jorels.countries.csv',
        'data/l10n_co_edi_jorels.departments.csv',
        'data/l10n_co_edi_jorels.municipalities.csv',
        'data/l10n_co_edi_jorels.postal_department.csv',
        'data/l10n_co_edi_jorels.postal_municipality.csv',
        'data/l10n_co_edi_jorels.postal.csv',
        'data/l10n_co_edi_jorels.payment_forms.csv',
        'data/l10n_co_edi_jorels.payment_methods.csv',
        'data/l10n_co_edi_jorels.payroll_periods.csv',
        'data/l10n_co_edi_jorels.subtype_workers.csv',
        'data/l10n_co_edi_jorels.type_contracts.csv',
        'data/l10n_co_edi_jorels.type_currencies.csv',
        'data/l10n_co_edi_jorels.type_document_identifications.csv',
        'data/l10n_co_edi_jorels.type_environments.csv',
        'data/l10n_co_edi_jorels.type_incapacities.csv',
        'data/l10n_co_edi_jorels.type_payroll_notes.csv',
        'data/l10n_co_edi_jorels.type_times.csv',
        'data/l10n_co_edi_jorels.type_workers.csv',
        'data/l10n_co_edi_jorels.type_organizations.csv',
        'data/l10n_co_edi_jorels.type_regimes.csv',
        'data/l10n_co_edi_jorels.type_liabilities.csv',
        # Vistas
        'views/config/res_company_payroll.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
