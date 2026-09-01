# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)

# Posibles ubicaciones del menú raíz/informes de Calidad segun la version
_PARENT_CANDIDATES = (
    'quality_control.menu_quality_reporting',
    'quality.menu_quality_reporting',
    'quality_control.menu_quality_root',
    'quality.menu_quality_root',
    'quality_control.menu_quality',
    'quality.menu_quality',
)


def post_init_hook(env):
    """Cuelga el menu del informe bajo la aplicacion Calidad.

    El xml_id del menu raiz de Calidad varia entre versiones/ediciones, por eso
    se resuelve en tiempo de instalacion en lugar de referenciarlo en el XML
    (una referencia inexistente abortaria la instalacion del modulo).
    """
    menu = env.ref('mrp_averias_report.menu_mrp_averia_report', raise_if_not_found=False)
    if not menu:
        return

    parent = False
    for xmlid in _PARENT_CANDIDATES:
        parent = env.ref(xmlid, raise_if_not_found=False)
        if parent:
            break

    if not parent:
        # Ultimo recurso: menu raiz cuyo nombre sea Calidad/Quality
        parent = env['ir.ui.menu'].sudo().search([
            ('parent_id', '=', False),
            ('name', 'in', ['Calidad', 'Quality']),
        ], limit=1)

    if parent:
        menu.sudo().write({'parent_id': parent.id})
        _logger.info('Menu de averias colgado bajo %s', parent.complete_name)
    else:
        _logger.warning(
            'No se encontro el menu raiz de Calidad. El informe de averias queda '
            'como menu de nivel superior; muevalo manualmente desde '
            'Ajustes > Tecnico > Elementos de menu.'
        )
