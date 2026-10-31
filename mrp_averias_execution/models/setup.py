# -*- coding: utf-8 -*-
from odoo import models


class MrpAveriasExecutionSetup(models.AbstractModel):
    """Reemplaza un post_init_hook, que en esta base nunca se ejecuta
    en la práctica porque el despliegue siempre es "actualizar" un
    módulo ya instalado, nunca "instalar de cero" (mismo motivo
    documentado en mrp_mold_management). Por eso la ubicación de menús
    y los ajustes de datos se hacen acá, invocados desde un archivo de
    datos sin noupdate (se re-ejecuta en cada actualización).

    No se hardcodea ningún xml_id de menú ajeno -- se busca por nombre
    en vivo, para no arriesgar una caída del ambiente de prueba
    compartido por un xml_id adivinado mal. Mismo criterio para el
    botón "Registrar avance" (fix_registrar_avance_button): se busca en
    vivo la vista que de verdad contiene el botón nativo "Iniciar"
    (button_start) y se hereda desde ahí.
    """
    _name = 'mrp.averias.execution.setup'
    _description = "Setup de mrp_averias_execution (menús y datos)"

    def _raiz_menu(self, nombres):
        return self.env['ir.ui.menu'].sudo().search([
            ('name', 'in', nombres), ('parent_id', '=', False)], limit=1)

    def _submenu(self, padre, nombres):
        if not padre:
            return padre
        return self.env['ir.ui.menu'].sudo().search([
            ('name', 'in', nombres), ('parent_id', '=', padre.id)],
            limit=1) or padre

    def _ubicar_menu(self, nombre, padre, xmlid_accion, secuencia):
        """Crea o actualiza un menú. Sin returns tempranos entre menús:
        antes, si el primer menú ya existía, la función salía y los
        menús agregados en versiones posteriores (p. ej. Averías
        Tipificadas) nunca se creaban al actualizar."""
        if not padre:
            return
        accion = self.env.ref(xmlid_accion, raise_if_not_found=False)
        if not accion:
            return
        Menu = self.env['ir.ui.menu'].sudo()
        valor = f'ir.actions.act_window,{accion.id}'
        existente = Menu.search([
            ('name', '=', nombre), ('parent_id', '=', padre.id)], limit=1)
        if existente:
            existente.write({'action': valor})
        else:
            Menu.create({
                'name': nombre,
                'parent_id': padre.id,
                'action': valor,
                'sequence': secuencia,
            })

    def fix_menu_placement(self):
        calidad = self._raiz_menu(['Calidad', 'Quality'])
        self._ubicar_menu(
            "Categorías de Avería",
            self._submenu(calidad, ['Configuración', 'Configuration']),
            'mrp_averias_execution.action_mrp_averia_categoria', 50)
        # Consulta operativa: directo bajo Calidad.
        self._ubicar_menu(
            "Registro de Averías", calidad,
            'mrp_averias_execution.action_mrp_averia_linea', 20)
        # Reemplaza el reporte viejo, en la misma ubicación.
        self._ubicar_menu(
            "Averías Tipificadas",
            self._submenu(calidad, ['Informes', 'Reportes', 'Reporting']),
            'mrp_averias_execution.action_mrp_averia_report', 30)

        fabricacion = self._raiz_menu(['Fabricación', 'Manufactura', 'Manufacturing'])
        self._ubicar_menu(
            "Bitácora de Seguimiento de tiempo",
            self._submenu(fabricacion, ['Informes', 'Reportes', 'Reporting']),
            'mrp_averias_execution.action_mrp_seguimiento_log', 90)

    def fix_catalogo_p03_p10(self):
        """Parte "P03 Ajuste de proceso / Proceso inestable (P10)" en
        dos razones (decisión de Laura, 22-10-2026):
          - P03 Ajuste de proceso: parada (Disponibilidad).
          - P10 Proceso inestable: Rendimiento, para escogerla como
            causa de un tramo lento.

        La categoría se cambia con loss_id (registro de categoría
        nativo) y NO escribiendo loss_type: loss_type es un related
        editable de la categoría, y escribirlo cambiaría la categoría
        compartida de todas las razones que la usan.

        Solo actúa si P03 conserva el nombre combinado (una vez); si
        Laura la edita después desde Configuración, no se toca.
        """
        Loss = self.env['mrp.workcenter.productivity.loss'].sudo()
        disponibilidad = self.env.ref('mrp.category_availability', raise_if_not_found=False)
        rendimiento = self.env.ref('mrp.category_performance', raise_if_not_found=False)

        p03 = self.env.ref(
            'mrp_averias_execution.loss_inyectoras_p03_ajuste_de_proceso_proceso_inestable_',
            raise_if_not_found=False)
        if p03 and "(P10)" in (p03.with_context(lang='en_US').name or ''):
            nombre = "P03 Ajuste de proceso"
            vals = {'name': nombre}
            if disponibilidad:
                vals['loss_id'] = disponibilidad.id
            p03.with_context(lang='en_US').write(vals)
            # El nombre es traducible: se deja igual en todos los idiomas
            # instalados, para que en español no siga el nombre viejo.
            p03.update_field_translations('name', {
                codigo: nombre
                for codigo, _n in self.env['res.lang'].get_installed()})

        if rendimiento and not Loss.search([
                ('name', '=ilike', 'P10%'),
                ('tipo_centro_trabajo', '=', 'inyectoras')], limit=1):
            Loss.create({
                'name': "P10 Proceso inestable",
                'loss_id': rendimiento.id,
                'tipo_centro_trabajo': 'inyectoras',
                'es_programada': False,
            })

    def fix_registrar_avance_button(self):
        """Agrega el botón "Registrar avance" en la orden de trabajo,
        junto a Iniciar/Pausar -- antes era un paso manual en Studio
        (ver README.md). Reemplazado por esto: busca en vivo la vista
        de mrp.workorder que contiene el botón nativo button_start
        ("Iniciar") y hereda ahí mismo, agregando el botón justo
        después. Nada de xml_id adivinado.
        """
        View = self.env['ir.ui.view'].sudo()

        propia = View.search([
            ('name', '=', 'mrp.workorder.view.form.registrar.avance'),
        ], limit=1)

        action = self.env.ref(
            'mrp_averias_execution.action_mrp_workorder_progress_wizard',
            raise_if_not_found=False)
        if not action:
            return

        boton_xml = (
            '<data>'
            '<xpath expr="//button[@name=\'button_start\']" position="after">'
            f'<button name="{action.id}" type="action" '
            'string="Registrar avance" class="btn-primary" '
            'invisible="state != \'progress\'"/>'
            '</xpath>'
            '</data>'
        )

        if propia:
            # Ya existe -- solo confirma que el botón siga apuntando a
            # la acción correcta (el id puede cambiar si el módulo se
            # reinstala desde cero en otra base).
            if propia.arch_db != boton_xml:
                propia.write({'arch': boton_xml})
            return

        candidata = View.search([
            ('model', '=', 'mrp.workorder'),
            ('type', '=', 'form'),
            ('active', '=', True),
            ('arch_db', 'like', 'button_start'),
        ], limit=1)
        if not candidata:
            # No se encontró ninguna vista con el botón nativo
            # Iniciar -- no se crea nada a ciegas. Laura puede seguir
            # el paso manual del README si esto llega a pasar.
            return

        View.create({
            'name': 'mrp.workorder.view.form.registrar.avance',
            'model': 'mrp.workorder',
            'inherit_id': candidata.id,
            'arch': boton_xml,
        })
