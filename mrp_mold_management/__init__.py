# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)

_PARENT_CANDIDATES = (
    'maintenance.menu_maintenance_title',
    'maintenance.menu_equipment_management',
    'maintenance.menu_equipment_form',
)

_MENU_XMLIDS = (
    'mrp_mold_management.menu_mold_equipment',
    'mrp_mold_management.menu_mold_revision_log',
)


def post_init_hook(env):
    """Cuelga los menus de Moldes bajo la app Mantenimiento.

    El xml_id exacto del menu raiz de Mantenimiento puede variar entre
    versiones/ediciones, por eso se resuelve en tiempo de instalacion en
    lugar de referenciarlo directamente en el XML (una referencia
    inexistente abortaria la instalacion del modulo completo).
    """
    parent = False
    for xmlid in _PARENT_CANDIDATES:
        parent = env.ref(xmlid, raise_if_not_found=False)
        if parent:
            break

    if not parent:
        parent = env['ir.ui.menu'].sudo().search([
            ('parent_id', '=', False),
            ('name', 'in', ['Mantenimiento', 'Maintenance']),
        ], limit=1)

    for xmlid in _MENU_XMLIDS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if not menu:
            continue
        if parent:
            menu.sudo().write({'parent_id': parent.id})
        else:
            _logger.warning(
                'No se encontro el menu raiz de Mantenimiento. "%s" queda '
                'como menu de nivel superior; muevalo manualmente desde '
                'Ajustes > Tecnico > Elementos de menu.', menu.name,
            )

    if parent:
        _logger.info('Menus de Moldes colgados bajo %s', parent.complete_name)
