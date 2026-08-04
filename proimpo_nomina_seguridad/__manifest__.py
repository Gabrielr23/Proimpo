# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Confidencialidad asientos de nomina",
    'summary': "Restringe los asientos del diario de nomina a un grupo cerrado",
    'description': "Marca uno o varios diarios como confidenciales (nomina). Solo los usuarios "
                   "del grupo 'Nomina Confidencial' pueden ver sus asientos y apuntes; el resto "
                   "de la contabilidad no los ve.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "18.0.1.0.0",
    'depends': ['account'],
    'data': [
        'security/nomina_seguridad_groups.xml',
        'views/account_journal_views.xml',
    ],
    'installable': True,
    'application': False,
}
