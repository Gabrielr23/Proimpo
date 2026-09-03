# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Aportes AFC y pension voluntaria (deduccion)",
    'summary': "Crea las reglas de deduccion de AFC y pension voluntaria y las mapea al certificado 220",
    'description': "Crea dos reglas de deduccion (AFC -> casilla 54, pension voluntaria -> casilla 53) "
                   "que leen los valores mensuales del contrato (campos Studio) y descuentan la mitad "
                   "en cada quincena (50/50). El certificado 220 acumula lo efectivamente descontado.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "19.0.1.0.0",
    'depends': ['proimpo_nomina_certificado'],
    'data': [],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
