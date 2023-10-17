##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2013-2016 'Interconsulting S.A. e Innovatecsa SAS.  (<http://www.interconsulting.com.co>).
#
#    This program is not free software: you can not redistribute it and/or modify
#    #
##############################################################################
{
    'name': 'Información Exógena',
    'version': '1.1',
    'author': 'Innovatecsa SAS. e OpensoftIT SAS',
    'category': 'Account',
    'depends': ['account'],
    'demo': [],
    'description': """
Este módulo permite generar la información Exógena para la DIAN
====================================================================

Las funcionalidades implementadas son:
-----------------------------------------------
    * Parametrización básica
    * Generación informes para validación
    * Generación archivos en la estructura especificada
    * 
    """,
    'data': [
       'views/account_exogenous_view.xml', 
       'data/activity_economic_data.xml',
       'security/ir.model.access.csv',
       'security/security.xml',
    ],
    'auto_install': False,
    'installable': True,
    'images': [],

}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
