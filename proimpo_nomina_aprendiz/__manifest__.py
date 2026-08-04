# -*- coding: utf-8 -*-
{
    'name': "PROIMPO - Aprendiz (estructura automática)",
    'summary': "Asigna sola la estructura Aprendiz Lectiva al calcular recibos de etapa lectiva",
    'description': "Cuando el contrato tiene Etapa = Lectiva, el recibo toma automáticamente la estructura 'Aprendiz Lectiva' al calcularlo, sin cambiarla a mano.",
    'author': "PROIMPO SAS",
    'license': "LGPL-3",
    'category': "Human Resources",
    'version': "18.0.1.0.0",
    'depends': ['proimpo_nomina_pila'],
    'data': ['data/params.xml'],
    'installable': True,
    'application': False,
}
