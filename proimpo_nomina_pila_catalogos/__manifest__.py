# -*- coding: utf-8 -*-
{
    'name': 'PROIMPO Nómina - Catálogos PILA (desplegables).',
    'version': '18.0.1.0.0',
    'summary': 'Listas desplegables (nombre + código) para EPS, AFP, ARL, Caja, municipio y clase de riesgo. Rellenan el código que ya usa el plano.',
    'author': 'PROIMPO SAS',
    'depends': ['proimpo_nomina_pila'],
    'data': [
        'security/ir.model.access.csv',
        'data/pila_arl_clase.xml',
        'data/pila_entidad.xml',
        'data/pila_municipio.xml',
        'views/hr_contract_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'license': 'LGPL-3',
}
