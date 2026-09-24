# -*- coding: utf-8 -*-
{
    'name': "Ejecución en Piso - Averías",
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': "Registrar avance, hoja de trabajo unificada de averías y "
               "razones de pérdida por Centro de Trabajo (PROIMPO)",
    'description': """
Migra a módulo las automatizaciones de averías que hoy viven en Studio, y
agrega:

  * Fase 1: automatizaciones de creación de control de calidad y
    totalización de averías (antes en Acciones automatizadas de Studio).
  * Fase 2: wizard "Registrar avance" para cerrar la línea de Seguimiento
    de tiempo en curso y abrir la siguiente sin pasar por "Pausado".
  * Fase 4: catálogo de categorías de avería (mrp.averia.categoria)
    filtrado por tipo de Centro de Trabajo, para la hoja de trabajo
    unificada "Registro Averías".
  * Fase 5: extensión del catálogo nativo de Razones de pérdida
    (mrp.workcenter.productivity.loss) con etiqueta de Centro de Trabajo
    e indicador Programada/No programada, cargado con las razones de
    PROIMPO (Inyectoras, Sopladoras, Impresión, Sellado).

No se toca ningún campo Studio existente (x_studio_*) — el módulo los
referencia por nombre técnico y construye la funcionalidad nueva encima.

El bloqueo/desbloqueo de Centro de Trabajo (antes "Fase 3" del plan)
queda deliberadamente fuera de este módulo por ahora.
""",
    'author': "PROIMPO S.A.S",
    'depends': [
        'mrp',
        'quality_control',
        'quality_mrp',
        'quality_control_worksheet',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_workorder_progress_wizard_views.xml',
        'views/mrp_averia_categoria_views.xml',
        'views/mrp_averia_linea_views.xml',
        'data/mrp_averia_categoria_data.xml',
        'data/mrp_workcenter_productivity_loss_data.xml',
        'data/menu_placement.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
