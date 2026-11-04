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

    # OJO: el nombre técnico de este campo Studio ("Línea Tiempo" en
    # quality.check) NO es fijo entre ambientes -- Studio le agrega un
    # sufijo numérico cuando detecta colisión al recrear el campo
    # (pasó en el rebuild del 2026-10-16: x_studio_linea_tiempo se
    # recreó como x_studio_linea_tiempo_1). Si en un futuro rebuild
    # vuelve a fallar "column ... does not exist" en
    # mrp_averia_report.py o acá, revisa el nombre técnico real en
    # Ajustes -> Técnico -> Campos (modelo quality.check, etiqueta
    # "Línea Tiempo") y actualízalo en LOS TRES lugares que lo usan:
    # esta constante, mrp_averia_linea.py (_sync_averias_a_seguimiento)
    # y la vista SQL de mrp_averia_report.py.
    LINEA_FIELD = 'x_studio_linea_tiempo_1'

    # --- Fase 5: filtrar loss_id por tipo de Centro de Trabajo -------
    workcenter_tipo = fields.Selection(
        related='workcenter_id.tipo_centro_trabajo',
        store=True, readonly=True, string="Tipo de CT (interno)")

    loss_id = fields.Many2one(
        domain="['|', ('tipo_centro_trabajo', '=', False), "
               "('tipo_centro_trabajo', '=', workcenter_tipo)]")

    # --- Fase A2: trazabilidad de origen ------------------------------
    registro_en_vivo = fields.Boolean(
        string="Registrado en vivo", copy=False, readonly=True,
        help="Marcado cuando el tramo se abrió en el momento (Iniciar o "
             "Registrar avance). Vacío = digitado después a mano.")

    # --- Fase A3: rendimiento del tramo (solo lectura, no se guarda) --
    rendimiento_tramo = fields.Float(
        string="Rendimiento (%)", compute='_compute_rendimiento_tramo',
        help="(buenas + averías) × estándar por pieza ÷ minutos del "
             "tramo. Vacío si el tramo no está cerrado o no hay "
             "estándar de ciclo.")

    # Campos que se registran en la bitácora al corregir un tramo
    # cerrado (solo los que existen en esta base).
    _CAMPOS_BITACORA = [
        ('date_start', "Inicio"),
        ('date_end', "Fin"),
        ('x_studio_cantidad', "Cantidad"),
        ('x_studio_averias', "Averías"),
        ('x_studio_reporta_averia', "¿Avería?"),
        ('loss_id', "Productividad"),
        ('employee_id', "Operario"),
    ]
    _CAMPOS_CLASIFICACION = {
        'x_studio_cantidad', 'x_studio_averias', 'date_start', 'date_end'}

    # --- Fase 1: disparadores que antes eran Acciones automatizadas --
    def write(self, vals):
        bitacora = self._bitacora_antes(vals)
        res = super().write(vals)
        if {'x_studio_averias', 'x_studio_reporta_averia'} & set(vals.keys()):
            self._crear_control_calidad()
        if 'x_studio_cantidad' in vals:
            self.mapped('workorder_id')._recompute_acumulado()
        if (self._CAMPOS_CLASIFICACION & set(vals.keys())
                and not self.env.context.get('sin_clasificacion')):
            self.filtered('date_end')._clasificar_rendimiento()
        self._bitacora_despues(bitacora)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._crear_control_calidad()
        records.mapped('workorder_id')._recompute_acumulado()
        return records

    def unlink(self):
        if not self.env.context.get('seguimiento_sin_log'):
            Log = self.env['mrp.seguimiento.log'].sudo()
            Log.create([{
                'accion': 'borrar',
                'workorder_id': rec.workorder_id.id,
                'workcenter_id': rec.workcenter_id.id,
                'linea_ref': rec.id,
                'tramo': rec._bitacora_tramo(),
                'valor_anterior': " · ".join(
                    f"{etiqueta}: {rec._bitacora_valor(campo)}"
                    for campo, etiqueta in rec._campos_bitacora()
                    if campo not in ('date_start', 'date_end')),
            } for rec in self])
        return super().unlink()

    # --- Fase A3: etiqueta nativa apagada ------------------------------
    @api.model
    def _perdida_plena(self):
        """"Tiempo de productividad plena" nativo (mrp.block_reason7)."""
        plena = self.env.ref('mrp.block_reason7', raise_if_not_found=False)
        return plena or self.env['mrp.workcenter.productivity.loss'].search(
            [('loss_type', '=', 'productive')], limit=1)

    @api.model
    def _perdida_reducida(self):
        """"Velocidad reducida" nativa (mrp.block_reason4)."""
        reducida = self.env.ref('mrp.block_reason4', raise_if_not_found=False)
        return reducida or self.env['mrp.workcenter.productivity.loss'].search(
            [('loss_type', '=', 'performance')], limit=1)

    @api.model
    def _umbral_rendimiento(self):
        valor = self.env['ir.config_parameter'].sudo().get_param(
            'mrp_averias_execution.umbral_rendimiento', '95')
        try:
            return float(valor)
        except ValueError:
            return 95.0

    def _close(self):
        """Pausar / Terminar nativos: cierra el tramo SIN partirlo en
        "Velocidad reducida" por tiempo acumulado de la OT (lógica
        nativa reemplazada; la clasificación se hace con piezas y
        minutos al guardar la cantidad)."""
        ahora = fields.Datetime.now()
        for timer in self:
            timer.write({'date_end': ahora})

    def _loss_type_change(self):
        """Onchange nativo al editar fechas/duración en la lista: ya no
        cambia la productividad por tiempo acumulado de la OT. Solo
        pone "Tiempo de productividad plena" si la línea no tiene."""
        self.ensure_one()
        if not self.loss_id:
            self.loss_id = self._perdida_plena()

    @api.depends('x_studio_cantidad', 'x_studio_averias', 'date_start',
                 'date_end', 'workorder_id')
    def _compute_rendimiento_tramo(self):
        for rec in self:
            rec.rendimiento_tramo = rec._calcular_rendimiento() or 0.0

    def _calcular_rendimiento(self, minutos=None):
        """Rendimiento en % o None si no se puede calcular."""
        self.ensure_one()
        if not self.workorder_id:
            return None
        segundos_pieza = self.workorder_id._averia_segundos_por_pieza()
        if minutos is None:
            if not (self.date_start and self.date_end):
                return None
            minutos = (self.date_end - self.date_start).total_seconds() / 60.0
        if not segundos_pieza or minutos <= 0:
            return None
        piezas = (self.x_studio_cantidad or 0) + (self.x_studio_averias or 0)
        return piezas * segundos_pieza / (minutos * 60.0) * 100.0

    def _clasificar_rendimiento(self, causa=None):
        """Tramo cerrado con producción: ≥ umbral → "Tiempo de
        productividad plena"; < umbral → la causa de tipo Rendimiento
        que haya escogido la persona, o "Velocidad reducida" nativa.

        No toca setups, paradas ni nada que no sea plena o de tipo
        Rendimiento. Un tramo sin buenas no se reclasifica aquí: el
        wizard pide el motivo de parada.
        """
        plena = self._perdida_plena()
        reducida = self._perdida_reducida()
        umbral = self._umbral_rendimiento()
        for rec in self:
            if not rec.date_end or not rec.loss_id:
                continue
            if rec.loss_id != plena and rec.loss_type != 'performance':
                continue
            if (rec.x_studio_cantidad or 0) <= 0:
                continue
            rendimiento = rec._calcular_rendimiento()
            if rendimiento is None:
                continue
            if rendimiento >= umbral:
                nueva = plena
            elif causa:
                nueva = causa
            elif rec.loss_type == 'performance':
                nueva = rec.loss_id
            else:
                nueva = reducida
            if nueva and nueva != rec.loss_id:
                rec.with_context(
                    sin_clasificacion=True, seguimiento_sin_log=True,
                ).write({'loss_id': nueva.id})

    # --- Fase B: bitácora de cambios ----------------------------------
    def _campos_bitacora(self):
        return [(c, e) for c, e in self._CAMPOS_BITACORA if c in self._fields]

    def _bitacora_valor(self, campo):
        self.ensure_one()
        valor = self[campo]
        tipo = self._fields[campo].type
        if tipo == 'many2one':
            return valor.display_name or ''
        if tipo == 'datetime':
            return (fields.Datetime.context_timestamp(self, valor)
                    .strftime('%d-%m-%Y %H:%M:%S') if valor else '')
        if tipo == 'boolean':
            return "Sí" if valor else "No"
        return '' if valor is False or valor is None else str(valor)

    def _bitacora_tramo(self):
        self.ensure_one()
        return "%s → %s" % (self._bitacora_valor('date_start'),
                            self._bitacora_valor('date_end') or "en curso")

    def _bitacora_antes(self, vals):
        """Valores anteriores de los tramos YA cerrados que se van a
        corregir. Lo que hace el propio módulo (wizard, sincronización
        de averías, clasificación) llega con seguimiento_sin_log."""
        if self.env.context.get('seguimiento_sin_log'):
            return []
        campos = [(c, e) for c, e in self._campos_bitacora() if c in vals]
        if not campos:
            return []
        return [(rec, rec._bitacora_tramo(),
                 {c: rec._bitacora_valor(c) for c, _e in campos}, campos)
                for rec in self.filtered('date_end')]

    def _bitacora_despues(self, bitacora):
        lineas = []
        for rec, tramo, antes, campos in bitacora:
            for campo, etiqueta in campos:
                nuevo = rec._bitacora_valor(campo)
                if nuevo != antes[campo]:
                    lineas.append({
                        'accion': 'editar',
                        'workorder_id': rec.workorder_id.id,
                        'workcenter_id': rec.workcenter_id.id,
                        'linea_ref': rec.id,
                        'tramo': tramo,
                        'campo': etiqueta,
                        'valor_anterior': antes[campo],
                        'valor_nuevo': nuevo,
                    })
        if lineas:
            self.env['mrp.seguimiento.log'].sudo().create(lineas)

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
