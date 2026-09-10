# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)

_ROOT_CANDIDATES = (
    'maintenance.menu_maintenance_title',
    'maintenance.menu_equipment_management',
    'maintenance.menu_equipment_form',
)


def _find_maintenance_root(env):
    for xmlid in _ROOT_CANDIDATES:
        m = env.ref(xmlid, raise_if_not_found=False)
        if m:
            return m
    return env['ir.ui.menu'].sudo().search([
        ('parent_id', '=', False),
        ('name', 'in', ['Mantenimiento', 'Maintenance']),
    ], limit=1)


def post_init_hook(env):
    """Ubica los menus de Moldes:
    - "Moldes" se cuelga DENTRO del submenu "Equipos" (junto a Centros de
      trabajo y Maquinas y herramientas), buscado por nombre bajo la raiz de
      Mantenimiento, sin depender de un xml_id que puede variar entre
      versiones/ediciones.
    - "Actualizacion de Especificaciones de Molde" (bitacora) queda como
      menu propio bajo la raiz de Mantenimiento: es una actividad de
      ingenieria de proceso, no de reparacion, y no tiene por que vivir
      dentro de "Equipos".
    """
    Menu = env['ir.ui.menu'].sudo()
    root = _find_maintenance_root(env)

    if not root:
        _logger.warning(
            'No se encontro el menu raiz de Mantenimiento. Los menus de '
            'Moldes quedan de nivel superior; muevalos manualmente desde '
            'Ajustes > Tecnico > Elementos de menu.'
        )
        return

    equipos = Menu.search([('name', '=', 'Equipos'), ('parent_id', '=', root.id)], limit=1)

    molde_menu = env.ref('mrp_mold_management.menu_mold_equipment', raise_if_not_found=False)
    if molde_menu:
        molde_menu.write({'parent_id': (equipos or root).id})

    bitacora_menu = env.ref('mrp_mold_management.menu_mold_revision_log', raise_if_not_found=False)
    if bitacora_menu:
        bitacora_menu.write({'parent_id': root.id})

    _logger.info(
        'Menu Moldes colgado bajo %s. Menu Bitacora colgado bajo %s.',
        (equipos or root).complete_name, root.complete_name,
    )
