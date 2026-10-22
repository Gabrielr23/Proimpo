# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Dominio de motivos de parada: lo que la persona escoge (manual) y no
# es de rendimiento. Incluye setups (tipo productivo del catálogo), que
# también son tramos sin buenas.
DOMINIO_PARADA = (
    "[('manual', '=', True), ('loss_type', '!=', 'performance'), "
    "'|', ('tipo_centro_trabajo', '=', False), "
    "('tipo_centro_trabajo', '=', workcenter_tipo)]")


class MrpWorkorderProgressWizard(models.TransientModel):
    """Wizard del botón "Registrar avance".

    Cierra el tramo abierto de Seguimiento de tiempo con su cantidad y
    abre el siguiente a la MISMA hora exacta (Fase A2): ya no usa
    Pausar + Iniciar, que dejaban segundos de hueco y solo cierran el
    tramo del usuario conectado (con otro usuario quedaban dos tramos
    abiertos a la vez).

    A1: operario opcional; por defecto el del tramo abierto, vacío si
        hubo cambio de turno (mrp_shift_resolver).
    A3: rendimiento y tipo sugerido; sin buenas = parada con motivo.
    A4: paradas declaradas dentro del tramo (motivo + minutos), que se
        separan al final del tramo, y hueco sin registrar antes del
        tramo, si lo hay.
    """
    _name = 'mrp.workorder.progress.wizard'
    _description = "Registrar avance de orden de trabajo"

    workorder_id = fields.Many2one(
        'mrp.workorder', required=True,
        default=lambda self: self.env.context.get('active_id'))
    linea_id = fields.Many2one(
        'mrp.workcenter.productivity', string="Tramo abierto", readonly=True)
    workcenter_tipo = fields.Selection(
        related='workorder_id.workcenter_id.tipo_centro_trabajo')
    tramo_inicio = fields.Datetime(
        related='linea_id.date_start', string="Tramo desde")

    cantidad = fields.Float(
        string="Buenas",
        help="Unidades buenas del tramo que se cierra (esta hora), no un "
             "acumulado.")
    reporta_averia = fields.Boolean(string="¿Avería?")

    # A1
    employee_id = fields.Many2one('hr.employee', string="Operario")
    cambio_turno = fields.Boolean(readonly=True)

    # A3
    minutos_tramo = fields.Float(
        string="Minutos del tramo", compute='_compute_rendimiento')
    minutos_operando = fields.Float(
        string="Minutos produciendo", compute='_compute_rendimiento')
    segundos_pieza = fields.Float(compute='_compute_rendimiento')
    piezas_estandar = fields.Float(
        string="Estándar del tramo (piezas)", compute='_compute_rendimiento',
        digits=(16, 0))
    rendimiento = fields.Float(
        string="Rendimiento (%)", compute='_compute_rendimiento',
        digits=(16, 0),
        help="Con las buenas. Las averías que se registren en la hoja se "
             "suman después y pueden subirlo.")
    sin_produccion = fields.Boolean(compute='_compute_rendimiento')
    es_lento = fields.Boolean(compute='_compute_rendimiento')
    tipo_sugerido = fields.Char(
        string="Tipo de productividad", compute='_compute_rendimiento')
    causa_id = fields.Many2one(
        'mrp.workcenter.productivity.loss', string="Causa de la velocidad",
        domain="[('loss_type', '=', 'performance'), "
               "'|', ('tipo_centro_trabajo', '=', False), "
               "('tipo_centro_trabajo', '=', workcenter_tipo)]",
        help="Opcional. Vacío = Velocidad reducida.")
    motivo_parada_id = fields.Many2one(
        'mrp.workcenter.productivity.loss', string="Motivo de la parada",
        domain=DOMINIO_PARADA)

    # A4
    parada_ids = fields.One2many(
        'mrp.workorder.progress.wizard.parada', 'wizard_id',
        string="Paradas dentro del tramo")
    hueco_inicio = fields.Datetime(string="Hueco desde", readonly=True)
    hueco_fin = fields.Datetime(string="Hueco hasta", readonly=True)
    hueco_minutos = fields.Float(string="Minutos sin registrar", readonly=True)
    motivo_hueco_id = fields.Many2one(
        'mrp.workcenter.productivity.loss', string="Motivo del hueco",
        domain=DOMINIO_PARADA,
        help="Opcional. Si se escoge, se crea una línea que llena el hueco.")

    # ------------------------------------------------------------------
    @api.model
    def _tramo_abierto(self, workorder):
        return self.env['mrp.workcenter.productivity'].search([
            ('workorder_id', '=', workorder.id),
            ('date_end', '=', False),
        ], limit=1, order='date_start desc')

    @api.model
    def _hubo_cambio_turno(self, linea, ahora):
        """True si el tramo abierto empezó en otro turno que el de
        ahora, según mrp_shift_resolver. Sin datos de turno: False."""
        if 'shift_name' not in linea._fields or not linea.shift_name:
            return False
        try:
            turno = self.env['mrp.shift.resolver'].resolve_shift(
                linea.workcenter_id, ahora)
        except Exception:
            return False
        if not turno or not turno.get('shift_name'):
            return False
        return (turno.get('shift_name') != linea.shift_name
                or turno.get('shift_date') != linea.shift_date)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        wo = self.env['mrp.workorder'].browse(
            res.get('workorder_id') or self.env.context.get('active_id'))
        if not wo:
            return res
        linea = self._tramo_abierto(wo)
        if not linea:
            return res
        res['linea_id'] = linea.id
        cambio = self._hubo_cambio_turno(linea, fields.Datetime.now())
        res['cambio_turno'] = cambio
        if not cambio and 'employee_id' in linea._fields and linea.employee_id:
            res['employee_id'] = linea.employee_id.id

        anterior = self.env['mrp.workcenter.productivity'].search([
            ('workorder_id', '=', wo.id),
            ('id', '!=', linea.id),
            ('date_end', '!=', False),
            ('date_end', '<=', linea.date_start),
        ], limit=1, order='date_end desc')
        if anterior:
            hueco = (linea.date_start - anterior.date_end).total_seconds()
            if hueco > 60:
                res.update({
                    'hueco_inicio': anterior.date_end,
                    'hueco_fin': linea.date_start,
                    'hueco_minutos': round(hueco / 60.0, 1),
                })
        return res

    @api.depends('cantidad', 'parada_ids.minutos', 'linea_id')
    def _compute_rendimiento(self):
        Productividad = self.env['mrp.workcenter.productivity']
        plena = Productividad._perdida_plena()
        reducida = Productividad._perdida_reducida()
        umbral = Productividad._umbral_rendimiento()
        ahora = fields.Datetime.now()
        for wiz in self:
            minutos = 0.0
            if wiz.linea_id and wiz.linea_id.date_start:
                minutos = max(
                    (ahora - wiz.linea_id.date_start).total_seconds() / 60.0, 0.0)
            paradas = sum(wiz.parada_ids.mapped('minutos'))
            operando = max(minutos - paradas, 0.0)
            segundos = wiz.workorder_id._averia_segundos_por_pieza() if wiz.workorder_id else 0.0
            estandar = operando * 60.0 / segundos if segundos else 0.0
            sin_produccion = (wiz.cantidad or 0) <= 0
            rendimiento = (wiz.cantidad / estandar * 100.0) if estandar else 0.0
            es_lento = bool(segundos) and not sin_produccion and rendimiento < umbral

            if sin_produccion:
                tipo = _("Parada: escoge el motivo")
            elif not segundos:
                tipo = "%s (%s)" % (plena.name, _("sin estándar de ciclo"))
            elif es_lento:
                tipo = reducida.name
            else:
                tipo = plena.name

            wiz.minutos_tramo = round(minutos, 1)
            wiz.minutos_operando = round(operando, 1)
            wiz.segundos_pieza = segundos
            wiz.piezas_estandar = estandar
            wiz.rendimiento = rendimiento
            wiz.sin_produccion = sin_produccion
            wiz.es_lento = es_lento
            wiz.tipo_sugerido = tipo

    # ------------------------------------------------------------------
    def _vals_linea(self, inicio, fin, perdida, en_vivo=True):
        """Valores de una línea nueva (parada o hueco) con la misma
        estructura que las nativas. El hueco se llena después de
        ocurrido: no queda como registrado en vivo."""
        vals = self.workorder_id._prepare_timeline_vals(0.0, inicio, fin)
        vals['loss_id'] = perdida.id
        vals['registro_en_vivo'] = en_vivo
        if 'employee_id' in self.env['mrp.workcenter.productivity']._fields:
            vals['employee_id'] = self.linea_id.employee_id.id or self.employee_id.id or False
        return vals

    def action_confirmar(self):
        self.ensure_one()
        wo = self.workorder_id
        Productividad = self.env['mrp.workcenter.productivity']
        sin_log = {'seguimiento_sin_log': True, 'sin_clasificacion': True}

        linea = self._tramo_abierto(wo)
        if not linea:
            raise UserError(_(
                "No hay un tramo abierto en Seguimiento de tiempo de esta "
                "orden. Usa \"Iniciar\" primero."))
        if linea != self.linea_id:
            raise UserError(_(
                "El tramo abierto cambió mientras tenías esta ventana "
                "abierta. Ciérrala y vuelve a registrar el avance."))

        ahora = fields.Datetime.now().replace(microsecond=0)
        minutos_tramo = (ahora - linea.date_start).total_seconds() / 60.0
        sin_produccion = (self.cantidad or 0) <= 0
        con_empleado = 'employee_id' in Productividad._fields

        # --- validaciones --------------------------------------------
        if minutos_tramo <= 0:
            raise UserError(_(
                "El tramo abierto empieza en el futuro (%(inicio)s). Corrige "
                "su hora de inicio en Seguimiento de tiempo.",
                inicio=fields.Datetime.context_timestamp(
                    self, linea.date_start).strftime('%d-%m-%Y %H:%M')))
        if sin_produccion and not self.motivo_parada_id:
            raise UserError(_(
                "El tramo no tiene unidades buenas, así que no puede quedar "
                "como productivo: escoge el motivo de la parada."))
        paradas = self.parada_ids if not sin_produccion else self.parada_ids.browse()
        for parada in paradas:
            if not parada.loss_id or parada.minutos <= 0:
                raise UserError(_(
                    "Cada parada necesita motivo y minutos mayores a 0."))
        total_paradas = sum(paradas.mapped('minutos'))
        if total_paradas >= minutos_tramo:
            raise UserError(_(
                "Las paradas suman %(p).0f min y el tramo dura %(t).0f min. "
                "Si todo el tramo fue parada, registra 0 buenas y escoge "
                "el motivo.", p=total_paradas, t=minutos_tramo))

        # --- 1. cerrar el tramo -------------------------------------
        fin_productivo = ahora - timedelta(minutes=total_paradas)
        vals_cierre = {
            'x_studio_cantidad': self.cantidad,
            'x_studio_reporta_averia': self.reporta_averia,
            'date_end': fin_productivo.replace(microsecond=0),
        }
        if sin_produccion:
            vals_cierre['loss_id'] = self.motivo_parada_id.id
        # Mismo turno: el operario escogido es el de este tramo (corrige,
        # p. ej., el que puso Iniciar con el usuario conectado). Cambio de
        # turno: el tramo que cierra conserva el operario del turno que sale.
        if con_empleado and not self.cambio_turno:
            vals_cierre['employee_id'] = self.employee_id.id or False
        linea.with_context(**sin_log).write(vals_cierre)
        if not sin_produccion:
            linea._clasificar_rendimiento(causa=self.causa_id or None)

        # --- 2. paradas declaradas, al final del tramo ----------------
        inicio = fin_productivo
        nuevas = []
        for parada in paradas:
            fin = inicio + timedelta(minutes=parada.minutos)
            nuevas.append(self._vals_linea(inicio, fin, parada.loss_id))
            inicio = fin

        # --- 3. hueco sin registrar antes del tramo -------------------
        if self.motivo_hueco_id and self.hueco_inicio and self.hueco_fin:
            nuevas.append(self._vals_linea(
                self.hueco_inicio, self.hueco_fin, self.motivo_hueco_id,
                en_vivo=False))

        if nuevas:
            Productividad.with_context(**sin_log).create(nuevas)

        # --- 4. abrir el tramo siguiente a la misma hora --------------
        # Otro tramo abierto del usuario conectado en esta orden (quedó
        # de antes) impediría abrir el nuevo: se cierra ahora.
        Productividad.search([
            ('workorder_id', '=', wo.id),
            ('date_end', '=', False),
            ('user_id', '=', self.env.uid),
        ])._close()
        vals_nuevo = wo._prepare_timeline_vals(wo.duration, ahora)
        if con_empleado:
            vals_nuevo['employee_id'] = self.employee_id.id or False
        Productividad.with_context(**sin_log).create(vals_nuevo)

        if self.reporta_averia:
            # Una hora puede tener varios tipos de avería: se abre de una
            # vez la hoja para cargarlos (mismo método del botón Tipificar).
            return linea.action_tipificar_averia()
        return {'type': 'ir.actions.act_window_close'}


class MrpWorkorderProgressWizardParada(models.TransientModel):
    _name = 'mrp.workorder.progress.wizard.parada'
    _description = "Parada declarada en Registrar avance"

    wizard_id = fields.Many2one(
        'mrp.workorder.progress.wizard', required=True, ondelete='cascade')
    workcenter_tipo = fields.Selection(related='wizard_id.workcenter_tipo')
    loss_id = fields.Many2one(
        'mrp.workcenter.productivity.loss', string="Motivo",
        domain=DOMINIO_PARADA)
    minutos = fields.Float(string="Minutos")
