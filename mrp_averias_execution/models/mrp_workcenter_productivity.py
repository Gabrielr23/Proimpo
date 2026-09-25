# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpWorkcenterProductivity(models.Model):
    """Extiende el Seguimiento de tiempo de la orden de trabajo.

    Fase 1: no se agrega ningun campo nuevo relacionado con averias aqui
    -- x_studio_cantidad, x_studio_averias, x_studio_reporta_averia y
    x_studio_quality_check_id ya existen como campos de Studio y se
    referencian por su nombre tecnico, sin tocarlos. Lo que se migra es
    la LOGICA que antes vivia en dos Acciones automatizadas de Studio.

    Fase 5: se agrega workcenter_tipo (related, solo lectura) y se
    reescribe el dominio del campo nativo loss_id para que solo
    muestre las Razones de perdida que aplican al tipo de Centro de
    Trabajo de esta linea.
    """
    _inherit = 'mrp.workcenter.productivity'

    LINEA_FIELD = 'x_studio_linea_tiempo'

    # --- Fase 5: filtrar loss_id por tipo de Centro de Trabajo -------
    workcenter_tipo = fields.Selection(
        related='workcenter_id.tipo_centro_trabajo',
        store=True, readonly=True, string="Tipo de CT (interno)")

    loss_id = fields.Many2one(
        domain="['|', ('tipo_centro_trabajo', '=', False), "
               "('tipo_centro_trabajo', '=', workcenter_tipo)]")

    # --- Fase 1: disparadores que antes eran Acciones automatizadas --
    def write(self, vals):
        res = super().write(vals)
        if {'x_studio_averias', 'x_studio_reporta_averia'} & set(vals.keys()):
            self._crear_control_calidad()
        if 'x_studio_cantidad' in vals:
            self.mapped('workorder_id')._recompute_acumulado()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._crear_control_calidad()
        records.mapped('workorder_id')._recompute_acumulado()
        return records

    def _crear_control_calidad(self):
        """Crea el quality.check y la linea de la hoja de trabajo
        unificada (mrp.averia.linea, Fase 4) cuando corresponde.

        Migrado de la primera Accion automatizada de Studio del
        instructivo original ("Paso 2 - Accion automatizada (crea
        check + hoja)"): misma busqueda de punto de control por
        producto y luego por categoria, mismo guardian anti-duplicados
        via el campo LINEA_FIELD en quality.check.
        """
        Check = self.env['quality.check'].sudo()
        Point = self.env['quality.point'].sudo()
        Linea = self.env['mrp.averia.linea'].sudo()

        for rec in self:
            # Antes se exigia x_studio_averias > 0 para crear el check.
            # Eso obligaba a que la cantidad ya existiera ANTES de abrir
            # la hoja -- pero la cantidad ahora se carga DENTRO de la
            # hoja (ver mrp_averia_linea.py, sync de vuelta a este
            # campo), asi que el disparador correcto es el check ¿Averia?
            # (x_studio_reporta_averia), no la cantidad.
            if not rec.x_studio_reporta_averia or not rec.workorder_id:
                continue
            if rec.x_studio_quality_check_id:
                continue

            existente = Check.search([(self.LINEA_FIELD, '=', rec.id)], limit=1)
            if existente:
                rec.sudo().write({'x_studio_quality_check_id': existente.id})
                continue

            wo = rec.workorder_id
            mo = wo.production_id
            product = mo.product_id
            company = rec.company_id or wo.company_id or self.env.company

            categ_ids = [
                int(c) for c in (product.categ_id.parent_path or '').split('/')
                if c
            ]

            point = Point.search([
                ('company_id', 'in', [False, company.id]),
                ('product_ids', 'in', product.ids),
            ], limit=1)
            if not point:
                point = Point.search([
                    ('company_id', 'in', [False, company.id]),
                    ('product_category_ids', 'in', categ_ids),
                ], limit=1)
            if not point:
                # Igual que en el original: sin punto de control
                # aplicable, no se crea nada (se deja para el boton
                # "Tipificar", que sí informa el motivo al usuario).
                continue

            qc = Check.create({
                'point_id': point.id,
                'team_id': point.team_id.id,
                'test_type_id': point.test_type_id.id,
                'product_id': product.id,
                'production_id': mo.id,
                'workorder_id': wo.id,
                'company_id': company.id,
                'user_id': rec.user_id.id or self.env.uid,
                self.LINEA_FIELD: rec.id,
            })

            Linea.create({'quality_check_id': qc.id})

            rec.sudo().write({'x_studio_quality_check_id': qc.id})

    def action_tipificar_averia(self):
        """Server action del boton "Tipificar".

        Reemplaza el id numerico fragil que Studio le puso al boton
        (name="1749") por una accion con external id fijo, definido
        por este modulo. Migrado de la segunda mitad del instructivo
        original ("Paso 3: crear accion de servidor"): crea el control
        de calidad si aun no existe (mismo camino de respaldo) y abre
        la hoja de trabajo unificada en una ventana emergente.
        """
        self.ensure_one()
        if not self.x_studio_reporta_averia:
            raise UserError(_(
                "Esta linea no registra averias. Guarda la orden de "
                "trabajo primero."))

        self._crear_control_calidad()
        qc = self.x_studio_quality_check_id
        if not qc:
            raise UserError(_(
                "No se pudo crear o encontrar el control de calidad "
                "para esta linea -- revisa que exista un punto de "
                "control aplicable al producto."))

        linea = self.env['mrp.averia.linea'].search(
            [('quality_check_id', '=', qc.id)], limit=1)
        if not linea:
            linea = self.env['mrp.averia.linea'].create(
                {'quality_check_id': qc.id})

        return {
            'type': 'ir.actions.act_window',
            'name': _("Registro Averías"),
            'res_model': 'mrp.averia.linea',
            'res_id': linea.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'create': True,
                'edit': True,
                'form_view_initial_mode': 'edit',
                'dialog_size': 'extra-large',
                'active_id': qc.id,
                'active_model': 'quality.check',
            },
        }
