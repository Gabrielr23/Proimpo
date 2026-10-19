# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class MrpOeeReportSetup(models.AbstractModel):
    _name = 'mrp.oee.report.setup'
    _description = ('Ubicación de los menús de OEE. Se reejecuta en CADA '
                    'actualización (post_init_hook solo corre al instalar).')

    def _find_parent(self, xmlids, names):
        Menu = self.env['ir.ui.menu'].sudo()
        for xmlid in xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                return menu
        raiz = Menu.search([('parent_id', '=', False),
                            ('name', 'in', ['Fabricación', 'Manufacturing'])], limit=1)
        if not raiz:
            return False
        return Menu.search([('parent_id', '=', raiz.id),
                            ('name', 'in', names)], limit=1) or raiz

    @api.model
    def fix_menu_placement(self):
        reporting = self._find_parent(
            ('mrp.menu_mrp_reporting', 'mrp.menu_mrp_report'),
            ['Informes', 'Reporting'])
        config = self._find_parent(
            ('mrp.menu_mrp_configuration',),
            ['Configuración', 'Configuration'])
        placements = (
            ('mrp_oee_report.menu_mrp_oee_dashboard', reporting),
            ('mrp_oee_report.menu_mrp_oee_report', reporting),
            ('mrp_oee_report.menu_mrp_oee_line', reporting),
            ('mrp_oee_report.menu_mrp_oee_loss', config),
        )
        for xmlid, parent in placements:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            if parent:
                menu.write({'parent_id': parent.id})
                _logger.info('Menú %s colgado bajo %s', xmlid, parent.complete_name)
            else:
                _logger.warning('No se encontró dónde colgar %s; muévalo desde '
                                'Ajustes > Técnico > Elementos de menú.', xmlid)
