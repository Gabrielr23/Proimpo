# -*- coding: utf-8 -*-
from odoo import models


class MrpAveriasExecutionSetup(models.AbstractModel):
    """Reemplaza un post_init_hook, que en esta base nunca se ejecuta
    en la práctica porque el despliegue siempre es "actualizar" un
    módulo ya instalado, nunca "instalar de cero" (mismo motivo
    documentado en mrp_mold_management). Por eso la ubicación del menú
    se corrige acá, invocada desde un archivo de datos sin noupdate
    (se re-ejecuta en cada actualización del módulo).

    No se hardcodea ningún xml_id de menú ajeno -- se busca por nombre
    en vivo, con reintentos, para no arriesgar una caída del ambiente
    de prueba compartido por un xml_id adivinado mal.
    """
    _name = 'mrp.averias.execution.setup'
    _description = "Setup de mrp_averias_execution (ubicación de menús)"

    def fix_menu_placement(self):
        Menu = self.env['ir.ui.menu'].sudo()

        raiz_calidad = Menu.search([
            ('name', 'in', ['Calidad', 'Quality']),
            ('parent_id', '=', False),
        ], limit=1)
        if not raiz_calidad:
            # No se encontró el menú raíz de Calidad -- no se crea nada
            # para no adivinar mal. Laura puede ubicarlo a mano desde
            # Studio si esto llega a pasar.
            return

        padre = Menu.search([
            ('name', 'in', ['Configuración', 'Configuration']),
            ('parent_id', '=', raiz_calidad.id),
        ], limit=1) or raiz_calidad

        action = self.env.ref(
            'mrp_averias_execution.action_mrp_averia_categoria',
            raise_if_not_found=False)
        if not action:
            return

        existente = Menu.search([
            ('name', '=', "Categorías de Avería"),
            ('parent_id', '=', padre.id),
        ], limit=1)
        if existente:
            existente.write({'action': f'ir.actions.act_window,{action.id}'})
            return

        Menu.create({
            'name': "Categorías de Avería",
            'parent_id': padre.id,
            'action': f'ir.actions.act_window,{action.id}',
            'sequence': 50,
        })

        # Registro de Averías -- lista de las hojas de trabajo (Fase 4).
        # Va directo bajo Calidad, no bajo Configuración, porque es
        # consulta operativa, no un catálogo a mantener.
        action_linea = self.env.ref(
            'mrp_averias_execution.action_mrp_averia_linea',
            raise_if_not_found=False)
        if not action_linea:
            return

        existente_linea = Menu.search([
            ('name', '=', "Registro de Averías"),
            ('parent_id', '=', raiz_calidad.id),
        ], limit=1)
        if existente_linea:
            existente_linea.write({
                'action': f'ir.actions.act_window,{action_linea.id}'})
            return

        Menu.create({
            'name': "Registro de Averías",
            'parent_id': raiz_calidad.id,
            'action': f'ir.actions.act_window,{action_linea.id}',
            'sequence': 20,
        })

        # Averías Tipificadas -- reemplaza el reporte viejo (mismo
        # nombre y misma ubicación que tenía: Calidad -> Informes),
        # ahora sobre datos propios de este módulo.
        action_report = self.env.ref(
            'mrp_averias_execution.action_mrp_averia_report',
            raise_if_not_found=False)
        if not action_report:
            return

        padre_informes = Menu.search([
            ('name', 'in', ['Informes', 'Reporting']),
            ('parent_id', '=', raiz_calidad.id),
        ], limit=1) or raiz_calidad

        existente_report = Menu.search([
            ('name', '=', "Averías Tipificadas"),
            ('parent_id', '=', padre_informes.id),
        ], limit=1)
        if existente_report:
            existente_report.write({
                'action': f'ir.actions.act_window,{action_report.id}'})
            return

        Menu.create({
            'name': "Averías Tipificadas",
            'parent_id': padre_informes.id,
            'action': f'ir.actions.act_window,{action_report.id}',
            'sequence': 30,
        })
