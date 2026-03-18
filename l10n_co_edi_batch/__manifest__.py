{
    'name': 'EDI Colombia - Envío en Lote',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Localizations/EDI',
    'summary': 'Envío en lote de documentos electrónicos a la DIAN via Carvajal',
    'description': """
        Permite seleccionar múltiples facturas/documentos soporte en la vista lista
        y enviarlos a la DIAN a través de Carvajal en segundo plano (background),
        sin bloquear la interfaz del usuario.
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
