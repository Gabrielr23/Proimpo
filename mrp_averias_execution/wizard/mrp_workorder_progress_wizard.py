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
    1.7.0: Desde / Hasta editables (registro al final del turno con el
        "horizontal"). Vienen prellenados: Desde = inicio del tramo
        abierto o fin del último tramo registrado; Hasta = ahora. Al
        confirmar NO se abre tramo nuevo, salvo "Sigue produciendo".
        Traslape con otro tramo de la misma orden: bloquea; con otra
        orden en la misma máquina: solo aviso.
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
    fecha_desde = fields.Datetime(
        string="Desde", required=True,
        help="Inicio del periodo que se registra. Por defecto, el inicio "
             "del tramo en curso o el fin del último tramo registrado.")
    fecha_hasta = fields.Datetime(
        string="Hasta", required=True, default=fields.Datetime.now,
        help="Fin del periodo que se registra. Por defecto, ahora.")
    sigue_produciendo = fields.Boolean(
        string="Sigue produciendo",
        help="Marcado: después de Hasta queda un tramo en curso (registro "
             "hora a hora). Sin marcar: no queda nada abierto (registro al "
             "final del turno).")
    aviso_traslape = fields.Text(compute='_compute_traslapes')

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
    hueco_inicio = fields.Datetime(string="Hueco desde", compute='_compute_hueco')
    hueco_fin = fields.Datetime(string="Hueco hasta", compute='_compute_hueco')
    hueco_minutos = fields.Float(string="Minutos sin registrar", compute='_compute_hueco')
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
        ultimo = self._ultimo_cerrado(wo)
        if linea:
            res['linea_id'] = linea.id
            res['fecha_desde'] = linea.date_start
            cambio = self._hubo_cambio_turno(linea, fields.Datetime.now())
            res['cambio_turno'] = cambio
            if not cambio and 'employee_id' in linea._fields and linea.employee_id:
                res['employee_id'] = linea.employee_id.id
        elif ultimo:
            res['fecha_desde'] = ultimo.date_end
            cambio = self._hubo_cambio_turno(ultimo, fields.Datetime.now())
            res['cambio_turno'] = cambio
            if not cambio and 'employee_id' in ultimo._fields and ultimo.employee_id:
                res['employee_id'] = ultimo.employee_id.id
        return res

    @api.model
    def _ultimo_cerrado(self, workorder, antes_de=None):
        dominio = [
            ('workorder_id', '=', workorder.id),
            ('date_end', '!=', False),
        ]
        if antes_de:
            dominio.append(('date_end', '<=', antes_de))
        return self.env['mrp.workcenter.productivity'].search(
            dominio, limit=1, order='date_end desc')

    @api.depends('fecha_desde', 'workorder_id')
    def _compute_hueco(self):
        for wiz in self:
            wiz.hueco_inicio = wiz.hueco_fin = False
            wiz.hueco_minutos = 0.0
            if not (wiz.fecha_desde and wiz.workorder_id):
                continue
            anterior = wiz._ultimo_cerrado(wiz.workorder_id, wiz.fecha_desde)
            if anterior:
                hueco = (wiz.fecha_desde - anterior.date_end).total_seconds()
                if hueco > 60:
                    wiz.hueco_inicio = anterior.date_end
                    wiz.hueco_fin = wiz.fecha_desde
                    wiz.hueco_minutos = hueco / 60.0

    def _lineas_que_cruzan(self, dominio_extra):
        """Líneas de Seguimiento de tiempo que se cruzan con
        [Desde, Hasta]. Una línea abierta cuenta hasta ahora."""
        self.ensure_one()
        ahora = fields.Datetime.now()
        lineas = self.env['mrp.workcenter.productivity'].search(dominio_extra + [
            ('date_start', '<', self.fecha_hasta),
            '|', ('date_end', '=', False), ('date_end', '>', self.fecha_desde),
        ])
        return lineas.filtered(lambda l: (l.date_end or ahora) > self.fecha_desde)

    def _texto_linea(self, linea):
        def hora(dt):
            return fields.Datetime.context_timestamp(self, dt).strftime('%d-%m %H:%M')
        fin = hora(linea.date_end) if linea.date_end else _("en curso")
        return "%s %s a %s (%s)" % (
            linea.workorder_id.production_id.name or '', hora(linea.date_start), fin,
            linea.loss_id.name or '')

    def _traslapes_misma_orden(self):
        self.ensure_one()
        return self._lineas_que_cruzan([
            ('workorder_id', '=', self.workorder_id.id),
            ('id', '!=', self.linea_id.id or 0),
        ])

    @api.depends('fecha_desde', 'fecha_hasta', 'workorder_id', 'linea_id')
    def _compute_traslapes(self):
        for wiz in self:
            avisos = []
            if wiz.fecha_desde and wiz.fecha_hasta and wiz.workorder_id \
                    and wiz.fecha_desde < wiz.fecha_hasta:
                misma = wiz._traslapes_misma_orden()
                if misma:
                    avisos.append(_(
                        "Se cruza con otro tramo de esta orden (no se podrá "
                        "guardar): %s", "; ".join(wiz._texto_linea(l) for l in misma[:3])))
                otras = wiz._lineas_que_cruzan([
                    ('workcenter_id', '=', wiz.workorder_id.workcenter_id.id),
                    ('workorder_id', '!=', wiz.workorder_id.id),
                ])
                if otras:
                    avisos.append(_(
                        "En esta máquina también hay tiempo de otras órdenes en "
                        "este periodo: %s", "; ".join(wiz._texto_linea(l) for l in otras[:3])))
            wiz.aviso_traslape = "\n".join(avisos) or False

    @api.depends('cantidad', 'parada_ids.minutos', 'fecha_desde', 'fecha_hasta')
    def _compute_rendimiento(self):
        Productividad = self.env['mrp.workcenter.productivity']
        plena = Productividad._perdida_plena()
        reducida = Productividad._perdida_reducida()
        umbral = Productividad._umbral_rendimiento()
        for wiz in self:
            minutos = 0.0
            if wiz.fecha_desde and wiz.fecha_hasta:
                minutos = max(
                    (wiz.fecha_hasta - wiz.fecha_desde).total_seconds() / 60.0, 0.0)
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

            wiz.minutos_tramo = minutos
            wiz.minutos_operando = operando
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
        ahora = fields.Datetime.now().replace(microsecond=0)

        linea = self._tramo_abierto(wo)
        if (linea or self.linea_id) and linea != self.linea_id:
            raise UserError(_(
                "El tramo en curso cambió mientras tenías esta ventana "
                "abierta. Ciérrala y vuelve a registrar el avance."))

        desde = self.fecha_desde.replace(microsecond=0)
        hasta = self.fecha_hasta.replace(microsecond=0)
        minutos_tramo = (hasta - desde).total_seconds() / 60.0
        sin_produccion = (self.cantidad or 0) <= 0
        con_empleado = 'employee_id' in Productividad._fields

        # --- validaciones --------------------------------------------
        if minutos_tramo <= 0:
            raise UserError(_("\"Hasta\" debe ser posterior a \"Desde\"."))
        if hasta > ahora + timedelta(minutes=1):
            raise UserError(_("\"Hasta\" no puede estar en el futuro."))
        misma = self._traslapes_misma_orden()
        if misma:
            raise UserError(_(
                "El periodo se cruza con otro tramo de esta orden:\n%s\n\n"
                "Ajusta Desde / Hasta, o corrige ese tramo en Seguimiento "
                "de tiempo.", "\n".join(self._texto_linea(l) for l in misma)))
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

        # --- 1. el tramo registrado ------------------------------------
        # En vivo solo si es el tramo en curso, sin tocar su inicio y
        # cerrado ahora (hora a hora). Con fechas puestas a mano, no.
        en_vivo = bool(linea) and linea.date_start == desde \
            and abs((ahora - hasta).total_seconds()) <= 300
        fin_productivo = (hasta - timedelta(minutes=total_paradas)).replace(microsecond=0)
        vals_tramo = {
            'x_studio_cantidad': self.cantidad,
            'x_studio_reporta_averia': self.reporta_averia,
            'date_start': desde,
            'date_end': fin_productivo,
            'registro_en_vivo': en_vivo,
        }
        if sin_produccion:
            vals_tramo['loss_id'] = self.motivo_parada_id.id
        # El operario escogido es el del tramo registrado. Excepción: hora
        # a hora con cambio de turno, el tramo que cierra conserva el
        # operario que sale y el escogido va al tramo nuevo.
        if con_empleado and not (self.sigue_produciendo and self.cambio_turno and linea):
            vals_tramo['employee_id'] = self.employee_id.id or False
        if linea:
            linea.with_context(**sin_log).write(vals_tramo)
            tramo = linea
        else:
            vals = wo._prepare_timeline_vals(0.0, desde, fin_productivo)
            vals.update(vals_tramo)
            if sin_produccion:
                vals['loss_id'] = self.motivo_parada_id.id
            tramo = Productividad.with_context(**sin_log).create(vals)
        if not sin_produccion:
            tramo._clasificar_rendimiento(causa=self.causa_id or None)

        # --- 2. paradas declaradas, al final del tramo ----------------
        inicio = fin_productivo
        nuevas = []
        for parada in paradas:
            fin = inicio + timedelta(minutes=parada.minutos)
            nuevas.append(self._vals_linea(inicio, fin, parada.loss_id, en_vivo=en_vivo))
            inicio = fin

        # --- 3. hueco sin registrar antes del tramo -------------------
        if self.motivo_hueco_id and self.hueco_inicio and self.hueco_fin:
            nuevas.append(self._vals_linea(
                self.hueco_inicio, self.hueco_fin, self.motivo_hueco_id,
                en_vivo=False))

        if nuevas:
            Productividad.with_context(**sin_log).create(nuevas)

        # --- 4. tramo siguiente, solo si sigue produciendo ------------
        if self.sigue_produciendo:
            Productividad.search([
                ('workorder_id', '=', wo.id),
                ('date_end', '=', False),
                ('user_id', '=', self.env.uid),
            ])._close()
            vals_nuevo = wo._prepare_timeline_vals(wo.duration, hasta)
            if con_empleado:
                vals_nuevo['employee_id'] = self.employee_id.id or False
            Productividad.with_context(**sin_log).create(vals_nuevo)
        if wo.state == 'ready':
            wo.state = 'progress'

        if self.reporta_averia:
            # Una hora puede tener varios tipos de avería: se abre de una
            # vez la hoja para cargarlos (mismo método del botón Tipificar).
            return tramo.action_tipificar_averia()
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
    minutos = fields.Float(
        string="Minutos",
        help="Duración de la parada en minutos:segundos (5:00 = 5 min).")
