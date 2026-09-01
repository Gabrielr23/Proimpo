# -*- coding: utf-8 -*-
{
    'name': 'PROIMPO Nómina Electrónica (DIAN, solución propia)',
    'version': '18.0.3.3.0',
    'summary': 'Genera el XML NominaIndividual (tipo 102) y de Ajuste (103) desde el recibo, '
               'calcula el CUNE, lo firma (XAdES) y lo transmite al set de pruebas DIAN '
               'reutilizando el motor nativo l10n_co_dian (SendTestSetAsync/GetStatusZip).',
    'author': 'PROIMPO SAS',
    'depends': ['l10n_co_hr_payroll_enterprise', 'l10n_co_dian'],
    'data': [
        'views/hr_payslip_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
