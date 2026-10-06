# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class MrpMoldManagementSetup(models.AbstractModel):
    _name = 'mrp.mold.management.setup'
    _description = ('Ubicación de menús y vistas opcionales. Sin tabla: es '
                    'el punto donde colgar lógica que debe reaplicarse en '
                    'CADA actualización, a diferencia de post_init_hook, que '
                    'solo corre en la primera instalación — y este módulo '
                    'siempre se despliega actualizando.')

    _ROOT_CANDIDATES = (
        'maintenance.menu_maintenance_title',
        'maintenance.menu_equipment_management',
        'maintenance.menu_equipment_form',
    )

    # Nombres posibles de la vista de formulario de solicitud de
    # mantenimiento. Varía entre versiones, y este proyecto ya tuvo dos
    # caídas de ambiente por referenciar un xml_id inexistente en XML
    # estático: aquí se resuelve en caliente y, si no está, se registra un
    # aviso en vez de abortar la instalación.
    _REQUEST_FORM_CANDIDATES = (
        'maintenance.hr_equipment_request_view_form',
        'maintenance.maintenance_request_view_form',
    )

    # ------------------------------------------------------------------
    @api.model
    def _find_root(self):
        for xmlid in self._ROOT_CANDIDATES:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                return menu
        return self.env['ir.ui.menu'].sudo().search([
            ('parent_id', '=', False),
            ('name', 'in', ['Mantenimiento', 'Maintenance']),
        ], limit=1)

    @api.model
    def fix_menu_placement(self):
        """Ubica los menús del módulo bajo la app Mantenimiento.

        El submenú "Equipos" se busca por NOMBRE bajo la raíz, no por
        xml_id, para no depender de nombres que cambian entre versiones.
        """
        Menu = self.env['ir.ui.menu'].sudo()
        root = self._find_root()
        if not root:
            _logger.warning(
                'No se encontró el menú raíz de Mantenimiento. Los menús de '
                'Moldes quedan de nivel superior; muévalos desde Ajustes > '
                'Técnico > Elementos de menú.')
            return

        equipos = Menu.search(
            [('name', '=', 'Equipos'), ('parent_id', '=', root.id)], limit=1)
        config = Menu.search([
            ('name', 'in', ['Configuración', 'Configuration']),
            ('parent_id', '=', root.id),
        ], limit=1)
        informes = Menu.search([
            ('name', 'in', ['Informes', 'Reporting', 'Reportes']),
            ('parent_id', '=', root.id),
        ], limit=1)

        ubicaciones = {
            'menu_mold_equipment': equipos or root,
            'menu_mold_away': root,
            'menu_mold_planning': root,
            'menu_mold_occupancy': root,
            'menu_mold_revision_log': root,
            'menu_mold_repair_report': informes or root,
            'menu_mold_zone': config or root,
        }
        for nombre, padre in ubicaciones.items():
            menu = self.env.ref('mrp_mold_management.%s' % nombre,
                                raise_if_not_found=False)
            if menu and padre:
                menu.sudo().write({'parent_id': padre.id})

        _logger.info('Menús de Moldes ubicados bajo %s.', root.complete_name)

    # ------------------------------------------------------------------
    @api.model
    def ensure_request_view(self):
        """Agrega los campos de taller a la solicitud de mantenimiento.

        Se crea en caliente, no en XML estático, porque el xml_id de esa
        vista no está confirmado en esta instancia. Si no se encuentra, el
        módulo se instala igual y los campos siguen existiendo en el
        modelo: solo habría que colocarlos con Studio.
        """
        padre = False
        for xmlid in self._REQUEST_FORM_CANDIDATES:
            padre = self.env.ref(xmlid, raise_if_not_found=False)
            if padre:
                break

        if not padre:
            _logger.warning(
                'No se encontró el formulario de solicitud de mantenimiento. '
                'Los campos de taller de reparación existen en el modelo, '
                'pero hay que agregarlos a la vista con Studio.')
            return

        arch = """
            <data>
                <xpath expr="//field[@name='equipment_id']" position="after">
                    <field name="is_mold_request" invisible="1"/>
                    <field name="repair_location_type"
                           invisible="not is_mold_request"/>
                    <field name="repair_partner_id"
                           invisible="repair_location_type != 'externo'"
                           options="{'no_quick_create': True}"/>
                    <field name="repair_days" readonly="1"
                           invisible="not is_mold_request"/>
                </xpath>
            </data>
        """

        View = self.env['ir.ui.view'].sudo()
        existente = View.search([
            ('name', '=', 'maintenance.request.form.mold'),
            ('model', '=', 'maintenance.request'),
        ], limit=1)
        vals = {
            'name': 'maintenance.request.form.mold',
            'model': 'maintenance.request',
            'inherit_id': padre.id,
            'arch': arch,
            'priority': 99,
        }
        try:
            if existente:
                existente.write(vals)
            else:
                View.create(vals)
            _logger.info('Vista de solicitud de mantenimiento extendida '
                         'sobre %s.', padre.xml_id or padre.id)
        except Exception as e:  # noqa: BLE001 - nunca debe tumbar la carga
            _logger.warning(
                'No se pudo extender el formulario de solicitud de '
                'mantenimiento (%s). Los campos existen en el modelo; '
                'agréguelos con Studio.', e)

    @api.model
    def post_update(self):
        self.fix_menu_placement()
        self.ensure_request_view()
