{
    'name': 'Workcenter Product Incompatibility',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Gestión de incompatibilidades entre productos y centros de trabajo',
    'description': """
        Este módulo permite definir qué centros de trabajo NO son compatibles
        con productos específicos, evitando su asignación en la planificación.
        
        Características:
        - Define productos incompatibles con workcenters
        - Validación automática en órdenes de producción
        - Advertencias en tiempo real
        - Sugerencias de workcenters alternativos
    """,
    'author': 'Tu Empresa',
    'website': 'https://www.tuempresa.com',
    'depends': [
        'mrp',
        'mrp_workorder',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/mrp_workcenter_views.xml',
        'views/mrp_workorder_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
