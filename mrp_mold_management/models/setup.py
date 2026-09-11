# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class MrpMoldManagementSetup(models.AbstractModel):
    _name = 'mrp.mold.management.setup'
    _description = ('Mrp Mold Management: ubicación de menús. No tiene tabla '
                    'ni datos propios — es solo un punto donde colgar lógica '
                    'que debe reaplicarse en CADA actualización del módulo, '
                    'a diferencia de post_init_hook (que solo corre en la '
                    'primera instalación y nunca en una actualización, que '
                    'es como este módulo se despliega en la práctica).')

    _ROOT_CANDIDATES = (
        'maintenance.menu_maintenance_title',
        'maintenance.menu_equipment_management',
        'maintenance.menu_equipment_form',
    )

    @api.model
    def fix_menu_placement(self):
        """Ubica los menús de Moldes:
        - "Moldes" dentro del submenú "Equipos" (junto a Centros de trabajo
          y Máquinas y herramientas), buscado por nombre bajo la raíz de
          Mantenimiento, sin depender de un xml_id que puede variar entre
          versiones/ediciones.
        - "Actualización de Especificaciones de Molde" (bitácora) queda
          como menú propio bajo la raíz de Mantenimiento: es ingeniería de
          proceso, no reparación, y no tiene por qué vivir dentro de
          "Equipos".

        Se llama desde data/menu_placement.xml con un <function>, que se
        reejecuta en cada actualización del módulo (a diferencia de un
        hook de instalación).
        """
        Menu = self.env['ir.ui.menu'].sudo()
        root = False
        for xmlid in self._ROOT_CANDIDATES:
            root = self.env.ref(xmlid, raise_if_not_found=False)
            if root:
                break
        if not root:
            root = Menu.search([
                ('parent_id', '=', False),
                ('name', 'in', ['Mantenimiento', 'Maintenance']),
            ], limit=1)

        if not root:
            _logger.warning(
                'No se encontró el menú raíz de Mantenimiento. Los menús de '
                'Moldes quedan de nivel superior; muévalos manualmente desde '
                'Ajustes > Técnico > Elementos de menú.'
            )
            return

        equipos = Menu.search(
            [('name', '=', 'Equipos'), ('parent_id', '=', root.id)], limit=1)

        molde_menu = self.env.ref(
            'mrp_mold_management.menu_mold_equipment', raise_if_not_found=False)
        if molde_menu:
            molde_menu.sudo().write({'parent_id': (equipos or root).id})

        bitacora_menu = self.env.ref(
            'mrp_mold_management.menu_mold_revision_log', raise_if_not_found=False)
        if bitacora_menu:
            bitacora_menu.sudo().write({'parent_id': root.id})

        _logger.info(
            'Menú Moldes colgado bajo %s. Menú Bitácora colgado bajo %s.',
            (equipos or root).complete_name, root.complete_name,
        )
