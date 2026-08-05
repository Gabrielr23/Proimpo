{
    'name': 'EDI Colombia - Envío en Lote',
    'version': '18.0.1.2.0',
    'category': 'Accounting/Localizations/EDI',
    'summary': 'Envío en lote de documentos electrónicos a la DIAN (Servicio Gratuito)',
    'description': """
        Permite seleccionar múltiples facturas/documentos soporte en la vista lista
        y enviarlos directamente a la DIAN usando el Servicio Gratuito de Odoo
        en segundo plano (background), sin bloquear la interfaz del usuario.
    """,
    'author': 'PROIMPO SAS',
    'depends': ['l10n_co_edi'],
    'data': [
        'data/server_action.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
