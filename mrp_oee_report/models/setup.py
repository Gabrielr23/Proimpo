# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class MrpOeeReportSetup(models.AbstractModel):
    _name = 'mrp.oee.report.setup'
    _description = ('Ubicación del menú del informe de OEE. Sin tabla: es un '
                    'punto donde colgar lógica que debe reaplicarse en CADA '
                    'actualización (post_init_hook solo corre en la primera '
                    'instalación, y este proyecto siempre se despliega '
                    'actualizando).')

    _ROOT_CANDIDATES = (
        'mrp.menu_mrp_reporting',
        'mrp.menu_mrp_report',
        'mrp.menu_mrp_root',
    )

    @api.model
    def fix_menu_placement(self):
        Menu = self.env['ir.ui.menu'].sudo()

        parent = False
        for xmlid in self._ROOT_CANDIDATES:
            parent = self.env.ref(xmlid, raise_if_not_found=False)
            if parent:
                break

        if not parent:
            raiz = Menu.search([
                ('parent_id', '=', False),
                ('name', 'in', ['Fabricación', 'Manufacturing']),
            ], limit=1)
            if raiz:
                parent = Menu.search([
                    ('parent_id', '=', raiz.id),
                    ('name', 'in', ['Informes', 'Reporting']),
                ], limit=1) or raiz

        menu = self.env.ref('mrp_oee_report.menu_mrp_oee_report',
                            raise_if_not_found=False)
        if not menu:
            return
        if parent:
            menu.write({'parent_id': parent.id})
            _logger.info('Menú de OEE colgado bajo %s', parent.complete_name)
        else:
            _logger.warning(
                'No se encontró el menú de Informes de Fabricación. El '
                'informe de OEE queda de nivel superior; muévalo desde '
                'Ajustes > Técnico > Elementos de menú.')
