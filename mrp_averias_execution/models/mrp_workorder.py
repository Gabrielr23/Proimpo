# -*- coding: utf-8 -*-
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models

# Colores de los niveles de rendimiento (fondo, texto).
COLORES = {
    'verde': ('#E6F4EA', '#17652B'),
    'amarillo': ('#FFF4CC', '#7A4F00'),
    'rojo': ('#FDECEA', '#A61B12'),
    'revisar': ('#EFE6F7', '#4E2475'),
    'na': ('#F3F4F6', '#4B5563'),
}


def fmt(numero, decimales=0):
    """Número con miles '.' y decimales ',' (como en planta)."""
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(',', '§').replace('.', ',').replace('§', '.')


def fmt_horas(horas):
    minutos = int(round(horas * 60))
    return "%d h %02d min" % (minutos // 60, minutos % 60)


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    # --- 1.8.0: panel de avance y avisos en la orden de trabajo -------
    panel_avance_html = fields.Html(
        string="Avance", compute='_compute_panel_avance', sanitize=False)
    avisos_html = fields.Html(
        string="Avisos", compute='_compute_panel_avance', sanitize=False)

    # --- 1.9.0: ciclo estándar meta (congelado) y ciclo real -------------
    ciclo_meta = fields.Float(
        string="Ciclo estándar meta (s/pieza)", readonly=True, copy=False,
        aggregator='avg',
        digits=(16, 2),
        help="Segundos por pieza que se exigen a esta orden. Se fija la "
             "primera vez que se registra tiempo en la orden (Iniciar, "
             "Registrar avance o una línea a mano) y ya no cambia aunque "
             "después se modifique el molde o la LdM.")
    ciclo_meta_origen = fields.Char(
        string="Origen del ciclo meta", readonly=True, copy=False)
    ciclo_real = fields.Float(
        string="Ciclo real (s/pieza)", compute='_compute_ciclo_real',
        aggregator='avg',
        store=True, digits=(16, 2),
        help="Lo que de verdad tardó la máquina en esta orden: segundos de "
             "los tramos con piezas ÷ (buenas + averías).")
    rendimiento_orden = fields.Float(
        string="Rendimiento (%)", compute='_compute_ciclo_real', store=True,
        digits=(16, 0), aggregator='avg',
        help="Ciclo meta ÷ ciclo real.")
    piezas_registradas = fields.Float(
        string="Piezas (buenas + averías)", compute='_compute_ciclo_real',
        store=True)

    def _recompute_acumulado(self):
        """Recalcula x_studio_acumulado sumando x_studio_cantidad de
        todas las lineas de Seguimiento de tiempo de esta orden.

        Migrado de la Accion automatizada de Studio del instructivo
        original ("Paso 3.2: acumulado de la orden de trabajo").
        Antes el campo se llamaba x_studio_acumulado_1; Laura lo
        renombro a x_studio_acumulado -- este modulo usa el nombre
        actual.
        """
        for wo in self:
            lineas = self.env['mrp.workcenter.productivity'].search([
                ('workorder_id', '=', wo.id),
            ])
            total = sum(lineas.mapped('x_studio_cantidad'))
            wo.write({'x_studio_acumulado': total})

    # --- Fase A3: sin etiqueta nativa al abrir ------------------------
    def _prepare_timeline_vals(self, duration, date_start, date_end=False):
        """Odoo nativo decide "Velocidad reducida" AL ABRIR el tramo,
        comparando el tiempo acumulado de toda la OT (setups y paradas
        incluidos) contra la duración esperada -- no mide velocidad.
        Acá todo tramo nace como "Tiempo de productividad plena"; la
        clasificación real se hace al cerrarlo, con piezas y minutos
        (ver MrpWorkcenterProductivity._clasificar_rendimiento).

        Un tramo que se abre sin fecha de fin es un temporizador que
        arranca ahora (Iniciar, Registrar avance): queda marcado como
        registrado en vivo.
        """
        vals = super()._prepare_timeline_vals(duration, date_start, date_end)
        plena = self.env['mrp.workcenter.productivity']._perdida_plena()
        if plena:
            vals['loss_id'] = plena.id
        if not date_end:
            vals['registro_en_vivo'] = True
        return vals

    def _averia_segundos_por_pieza(self):
        """Ciclo estándar meta en segundos por pieza. Si la orden ya lo
        tiene congelado (1.9.0), ese; si no, el que dan hoy el molde o
        la operación (ver _ciclo_meta_vivo)."""
        self.ensure_one()
        if self.ciclo_meta:
            return self.ciclo_meta
        return self._ciclo_meta_vivo()[0]

    def _ciclo_meta_vivo(self):
        """(segundos por pieza, origen) con los datos de hoy.

        Con molde (módulo de moldes, si está instalado): la misma regla
        que usa ese módulo para el objetivo por hora (_mold_minutes):
        respeta la variante del molde de la operación (ciclo medido ÷
        unidades por disparo) y, si no hay variante, ciclo efectivo ÷
        cavidades. Sin molde: duración por defecto de la operación de la
        LdM (time_cycle_manual, minutos por unidad). La eficiencia del
        centro de trabajo no aplica: la meta es el ciclo ideal.
        """
        self.ensure_one()
        if 'mold_id' in self._fields and self.mold_id:
            mold = self.mold_id
            variante = self['mold_variant_id'] if 'mold_variant_id' in self._fields else False
            minutos = 0.0
            if hasattr(self, '_mold_minutes'):
                minutos = self._mold_minutes(mold) or 0.0
            if not minutos:
                ciclo = mold['cycle_time_effective'] if 'cycle_time_effective' in mold._fields else 0.0
                cavidades = mold['cavity_count'] if 'cavity_count' in mold._fields else 0
                if ciclo and cavidades:
                    minutos = ciclo / cavidades / 60.0
            if minutos:
                spp = minutos * 60.0
                if variante and self.operation_id and mold == self.operation_id.mold_id:
                    origen = _("Molde %(m)s, variante %(v)s: %(c)s s por disparo",
                               m=mold.display_name, v=variante.name,
                               c=fmt(variante.cycle_time or 0.0, 1))
                else:
                    ciclo = mold['cycle_time_effective'] if 'cycle_time_effective' in mold._fields else 0.0
                    cav = mold['cavity_count'] if 'cavity_count' in mold._fields else 0
                    origen = _("Molde %(m)s: %(c)s s ÷ %(n)s cavidades",
                               m=mold.display_name, c=fmt(ciclo, 1), n=cav)
                return spp, origen
        if self.operation_id and self.operation_id.time_cycle_manual:
            return (self.operation_id.time_cycle_manual * 60.0,
                    _("Operación %(o)s de la LdM: %(m)s min por unidad",
                      o=self.operation_id.name,
                      m=fmt(self.operation_id.time_cycle_manual, 3)))
        return 0.0, False

    def _congelar_ciclo_meta(self):
        """Fija el ciclo meta la primera vez que la orden tiene tiempo
        registrado. No lo vuelve a cambiar."""
        for wo in self.filtered(lambda w: not w.ciclo_meta):
            spp, origen = wo._ciclo_meta_vivo()
            if spp:
                wo.sudo().write({'ciclo_meta': spp, 'ciclo_meta_origen': origen})

    def action_actualizar_ciclo_meta(self):
        """Solo para corregir una meta mal tomada (molde equivocado al
        iniciar): vuelve a tomarla del molde o de la LdM de hoy."""
        for wo in self:
            spp, origen = wo._ciclo_meta_vivo()
            wo.sudo().write({'ciclo_meta': spp or 0.0, 'ciclo_meta_origen': origen or False})
        return True

    # --- 1.10.0: tiempos con la misma regla del tablero OEE ---------------
    def _clase_oee(self, linea):
        """Igual que mrp_oee_report: 'autorizada' (Parada autorizada),
        'marcha' (motivo de tipo Productivo, Rendimiento o Calidad) o
        'parada' (Disponibilidad no autorizada)."""
        if self._es_autorizada(linea):
            return 'autorizada'
        tipo = linea.loss_id.loss_type if linea.loss_id else 'productive'
        if tipo in ('productive', 'performance', 'quality'):
            return 'marcha'
        return 'parada'

    def _cifras_oee(self):
        """Minutos y piezas de los tramos cerrados, como el tablero OEE.
        Un tramo de más de horas_max_tramo (12 h) es un registro olvidado:
        no cuenta (ni tiempo ni piezas) y sale en los avisos."""
        self.ensure_one()
        horas_max = self.env['mrp.workcenter.productivity']._parametro('horas_max_tramo', 12)
        c = {'marcha': 0.0, 'parada': 0.0, 'autorizada': 0.0,
             'buenas': 0.0, 'averias': 0.0, 'buenas_marcha': 0.0, 'olvidados': 0, 'cruzados': 0}
        fin_max = None
        for linea in self.time_ids.filtered(
                lambda l: l.date_start and l.date_end).sorted('date_start'):
            minutos = (linea.date_end - linea.date_start).total_seconds() / 60.0
            if minutos > horas_max * 60.0:
                c['olvidados'] += 1
                continue
            # Tramos cruzados de la misma orden: el reloj cuenta una vez
            # (como el tablero); las piezas cuentan completas.
            inicio = max(linea.date_start, fin_max) if fin_max else linea.date_start
            if fin_max and linea.date_start < fin_max:
                c['cruzados'] += 1
            minutos = max((linea.date_end - inicio).total_seconds() / 60.0, 0.0)
            fin_max = max(fin_max, linea.date_end) if fin_max else linea.date_end
            clase = self._clase_oee(linea)
            c[clase] += minutos
            c['buenas'] += linea.x_studio_cantidad or 0.0
            c['averias'] += linea.x_studio_averias or 0.0
            if clase == 'marcha':
                c['buenas_marcha'] += linea.x_studio_cantidad or 0.0
        c['piezas'] = c['buenas'] + c['averias']
        return c

    @api.depends('ciclo_meta', 'time_ids.x_studio_cantidad', 'time_ids.x_studio_averias',
                 'time_ids.date_start', 'time_ids.date_end', 'time_ids.loss_id')
    def _compute_ciclo_real(self):
        """1.10.0: tiempo en marcha (regla del tablero OEE) ÷ piezas."""
        for wo in self:
            c = wo._cifras_oee()
            segundos = c['marcha'] * 60.0
            wo.piezas_registradas = c['piezas']
            wo.ciclo_real = segundos / c['piezas'] if c['piezas'] and segundos else 0.0
            wo.rendimiento_orden = (wo.ciclo_meta / wo.ciclo_real * 100.0
                                    if wo.ciclo_meta and wo.ciclo_real else 0.0)

    @staticmethod
    def _es_autorizada(linea):
        """Parada autorizada del tablero OEE (mrp_oee_report). Sin ese
        módulo instalado, ninguna lo es."""
        perdida = linea.loss_id
        return bool('oee_authorized_stop' in perdida._fields and perdida.oee_authorized_stop)

    # --- 1.6.2: el inverso nativo de "Duración real" borraba tramos ---
    # Tolerancia (minutos) para la diferencia entre la duración que manda
    # el formulario y la que calcula el servidor cuando hay un tramo
    # abierto: el formulario la calcula segundos antes de guardar.
    _TOLERANCIA_DURACION = 1.0

    def write(self, vals):
        """Al guardar el formulario con líneas de Seguimiento de tiempo
        nuevas o editadas, el cliente también manda "Duración real"
        (duration), calculada en el onchange unos segundos antes. Como
        duration tiene inverso (_set_duration), Odoo compara ese valor
        con el que calcula al guardar y "quita" la diferencia empezando
        por el tramo más nuevo: una línea agregada a mano sin Fin dura 0
        y se borra (si tenía ¿Avería?, el control de calidad la
        referencia y el borrado falla con un error de llave foránea; sin
        avería, la línea desaparecía en silencio).

        Si en la misma escritura vienen las líneas, ellas mandan: la
        duración se recalcula sola a partir de ellas.
        """
        if 'time_ids' in vals and 'duration' in vals:
            vals = dict(vals)
            vals.pop('duration')
        return super().write(vals)

    def _set_duration(self):
        """Segundo seguro para el mismo problema (por ejemplo, si solo
        llega duration): con un tramo abierto, una diferencia menor a la
        tolerancia es el reloj corriendo entre el onchange y el
        guardado, no un cambio pedido por el usuario. Se ignora."""
        ajustar = self.browse()
        for order in self:
            delta = order.duration - order.get_duration()
            abierta = order.time_ids.filtered(lambda t: not t.date_end)
            if abierta and abs(delta) < self._TOLERANCIA_DURACION:
                continue
            ajustar |= order
        return super(MrpWorkorder, ajustar)._set_duration()

    # --- 1.8.0: panel de avance -------------------------------------------
    def _resumen_avance(self):
        """Cifras del panel. 1.10.0: rendimiento, ritmo y OEE con la regla
        del tablero OEE: tiempo en marcha = tramos cerrados con motivo
        Productivo, Rendimiento o Calidad; sin paradas autorizadas ni
        tramos de más de 12 h."""
        self.ensure_one()
        lineas = self.time_ids
        buenas = sum(lineas.mapped('x_studio_cantidad'))
        averias = sum(lineas.mapped('x_studio_averias'))
        c = self._cifras_oee()
        segundos_prod = c['marcha'] * 60.0
        piezas_prod = c['piezas']
        buenas_prod = c['buenas']
        spp = self._averia_segundos_por_pieza()
        cantidad = self.qty_production or 0.0
        rend = (piezas_prod * spp / segundos_prod * 100.0) if spp and segundos_prod and piezas_prod else None
        # OEE de la orden = Disponibilidad × Rendimiento × Calidad.
        cargado = c['marcha'] + c['parada']
        disp = (c['marcha'] / cargado * 100.0) if cargado else None
        cal = (c['buenas'] / piezas_prod * 100.0) if piezas_prod else None
        oee = (disp * rend * cal / 10000.0) if None not in (disp, rend, cal) else None
        faltan = max(cantidad - buenas, 0.0)
        horas_ritmo = (faltan / (buenas_prod / segundos_prod) / 3600.0
                       if buenas_prod and segundos_prod else None)
        horas_std = faltan * spp / 3600.0 if spp else None
        # Proyección contra la DURACIÓN planeada, no contra fechas: Odoo
        # sobrescribe las fechas de la OT al pulsar Iniciar o Marcar como
        # hecha y no guarda las originales (decisión 17-11, opción B).
        horas = horas_ritmo if horas_ritmo is not None else horas_std
        # 1.9.0: las paradas autorizadas (no había producción planeada,
        # setup o cambio dentro de su máximo, purga...) no cuentan contra
        # la orden. Para comparar igual, al plan se le quita el setup del
        # centro de trabajo que Odoo incluye en la duración esperada.
        hay_autorizadas = 'oee_authorized_stop' in self.env['mrp.workcenter.productivity.loss']._fields
        cerradas = lineas.filtered(lambda l: l.date_start and l.date_end)
        autorizadas = cerradas.filtered(self._es_autorizada)
        minutos_autorizados = sum(
            (l.date_end - l.date_start).total_seconds() / 60.0 for l in autorizadas)
        registrada = sum(
            (l.date_end - l.date_start).total_seconds() / 60.0 for l in cerradas) - minutos_autorizados
        setup_plan = 0.0
        if hay_autorizadas and self.workcenter_id:
            setup_plan = (self.workcenter_id.time_start or 0.0) + (self.workcenter_id.time_stop or 0.0)
        planeada = max((self.duration_expected or 0.0) - setup_plan, 0.0)
        proyectada = registrada + (horas or 0.0) * 60.0
        diferencia = proyectada - planeada if planeada else None
        fin_estimado = fields.Datetime.now() + timedelta(hours=horas) if horas else None
        tolerancia = self.env['mrp.workcenter.productivity']._parametro(
            'tolerancia_cantidad', 10) / 100.0
        if cantidad and faltan <= 0:
            estado = 'completa'
        elif diferencia is None or horas is None:
            estado = 'sin_plan'
        elif diferencia <= 0:
            estado = 'a_tiempo'
        elif diferencia <= planeada * tolerancia:
            estado = 'en_riesgo'
        else:
            estado = 'retrasada'
        return {
            'cantidad': cantidad, 'buenas': buenas, 'averias': averias,
            'avance': (buenas / cantidad * 100.0) if cantidad else 0.0,
            'averias_pct': (averias / (buenas + averias) * 100.0) if (buenas + averias) else 0.0,
            'spp': spp, 'rend': rend, 'faltan': faltan,
            'horas_ritmo': horas_ritmo, 'horas_std': horas_std,
            'estado': estado, 'piezas': buenas + averias,
            'planeada': planeada, 'proyectada': proyectada,
            'setup_plan': setup_plan, 'minutos_autorizados': minutos_autorizados,
            'ciclo_real': (segundos_prod / piezas_prod) if piezas_prod and segundos_prod else None,
            'diferencia': diferencia, 'fin_estimado': fin_estimado,
            'disp': disp, 'cal': cal, 'oee': oee, 'oee_cifras': c,
            'oee_meta': (self.workcenter_id.oee_target or 0.0) if self.workcenter_id else 0.0,
        }

    def _fecha_local(self, valor, formato='%d-%m %H:%M'):
        return fields.Datetime.context_timestamp(self, valor).strftime(formato)

    @staticmethod
    def _tarjeta(titulo, valor, detalle, nivel='na', extra=''):
        fondo, texto = COLORES[nivel]
        borde = '#E5E7EB' if nivel == 'na' else fondo
        if nivel == 'na':
            fondo, texto = '#FFFFFF', '#1F2937'
        return Markup(
            '<div style="flex:1 1 200px;min-width:180px;border:1px solid {borde};background:{fondo};'
            'border-radius:6px;padding:10px 12px;display:flex;flex-direction:column;gap:4px">'
            '<span style="font-size:12px;color:#4B5563">{titulo}</span>'
            '<strong style="font-size:18px;color:{texto}">{valor}</strong>{extra}'
            '<span style="font-size:12px;color:#4B5563">{detalle}</span></div>'
        ).format(borde=borde, fondo=fondo, texto=texto, titulo=titulo,
                 valor=valor, detalle=detalle, extra=extra)

    @api.depends('time_ids', 'time_ids.x_studio_cantidad', 'time_ids.x_studio_averias',
                 'time_ids.date_start', 'time_ids.date_end', 'time_ids.loss_id',
                 'qty_production', 'duration_expected')
    def _compute_panel_avance(self):
        Prod = self.env['mrp.workcenter.productivity']
        for wo in self:
            if not wo.id or not wo.time_ids:
                wo.panel_avance_html = False
                wo.avisos_html = False
                continue
            r = wo._resumen_avance()
            barra = Markup(
                '<div style="height:8px;background:#E5E7EB;border-radius:4px">'
                '<div style="height:8px;width:{w}%;background:#714B67;border-radius:4px"></div></div>'
            ).format(w=min(round(r['avance']), 100))
            tarjetas = [wo._tarjeta(
                _("Avance (buenas)"),
                "%s / %s · %s %%" % (fmt(r['buenas']), fmt(r['cantidad']), fmt(r['avance'])),
                _("Averías %(n)s (%(p)s %%)", n=fmt(r['averias']), p=fmt(r['averias_pct'], 1)),
                extra=barra)]
            if r['rend'] is not None or r['disp'] is not None:
                tarjetas.append(wo._tarjeta_oee(r))
            if r['spp']:
                origen = wo.ciclo_meta_origen or wo._ciclo_meta_vivo()[1] or ''
                congelado = _("fijado al iniciar") if wo.ciclo_meta else _("aún no fijado")
                real = Markup('')
                if r['ciclo_real']:
                    real = Markup(
                        '<strong style="font-size:18px;color:#1F2937">{t}</strong>'
                        '<span style="font-size:12px;color:#4B5563">{h}</span>').format(
                        t=_("Real: %s s / pieza", fmt(r['ciclo_real'], 1)),
                        h=_("%s piezas/h · tiempo en marcha", fmt(3600.0 / r['ciclo_real'])))
                tarjetas.append(wo._tarjeta(
                    _("Ciclo"), _("Meta: %s s / pieza", fmt(r['spp'], 1)),
                    "", extra=Markup(
                        '<span style="font-size:12px;color:#4B5563">{h} · {o} ({c})</span>{real}').format(
                        h=_("%s piezas/h", fmt(3600.0 / r['spp'])), o=origen, c=congelado, real=real)))
            etiquetas = {
                'completa': (_("Completa"), 'verde'),
                'a_tiempo': (_("A tiempo"), 'verde'),
                'en_riesgo': (_("En riesgo"), 'amarillo'),
                'retrasada': (_("Retrasada"), 'rojo'),
                'sin_plan': (_("Sin proyección"), 'na'),
            }
            etiqueta, nivel = etiquetas[r['estado']]
            partes = []
            if r['diferencia'] is not None and r['estado'] != 'completa':
                if r['diferencia'] > 0:
                    partes.append(_("Al ritmo actual va %s por encima de lo planeado",
                                    fmt_horas(r['diferencia'] / 60.0)))
                else:
                    partes.append(_("Al ritmo actual va %s por debajo de lo planeado",
                                    fmt_horas(-r['diferencia'] / 60.0)))
            if r['faltan'] > 0 and r['horas_ritmo'] is not None:
                partes.append(_("faltan %s de máquina", fmt_horas(r['horas_ritmo'])))
            if r['faltan'] > 0 and r['horas_std'] is not None:
                partes.append(_("%s al estándar", fmt_horas(r['horas_std'])))
            if r['fin_estimado'] and r['estado'] != 'completa':
                partes.append(_("fin estimado %s", wo._fecha_local(r['fin_estimado'], '%d-%m %H:%M')))
            if r['planeada']:
                partes.append(_("duración planeada %s", fmt_horas(r['planeada'] / 60.0)))
            if r['setup_plan'] or r['minutos_autorizados']:
                partes.append(_("sin setup del plan (%(s)s) ni paradas autorizadas (%(a)s)",
                                s=fmt_horas(r['setup_plan'] / 60.0),
                                a=fmt_horas(r['minutos_autorizados'] / 60.0)))
            tarjetas.append(wo._tarjeta(_("Proyección"), etiqueta, " · ".join(partes), nivel))
            wo.panel_avance_html = Markup(
                '<div style="display:flex;flex-wrap:wrap;gap:12px">%s</div>') % Markup('').join(tarjetas)
            wo.avisos_html = wo._avisos_orden(r) or False

    def _nivel_oee(self, valor, meta):
        """Verde desde la meta OEE del centro de trabajo; amarillo hasta
        15 puntos por debajo; rojo más abajo."""
        if valor is None:
            return 'na'
        meta = meta or 90.0
        if valor >= meta:
            return 'verde'
        if valor >= meta - 15.0:
            return 'amarillo'
        return 'rojo'

    def _tarjeta_oee(self, r):
        """Tarjeta Rendimiento y OEE: rendimiento arriba (como en 1.8.0) y,
        debajo, Disponibilidad × Rendimiento × Calidad = OEE."""
        Prod = self.env['mrp.workcenter.productivity']
        c = r['oee_cifras']

        def pct(valor):
            return '—' if valor is None else '%s %%' % fmt(valor)

        def chip(valor, nivel, grande=False):
            fondo, texto = COLORES[nivel]
            if nivel == 'na':
                fondo, texto = '#F3F4F6', '#1F2937'
            return Markup(
                '<span style="background:{f};color:{t};border-radius:4px;padding:0 6px;white-space:nowrap;'
                'font-weight:700;font-size:{s}px">{v}</span>').format(
                f=fondo, t=texto, s=18 if grande else 13, v=pct(valor))

        def fila(nombre, valor, nivel, ayuda):
            return Markup(
                '<div title="{a}" style="display:flex;justify-content:space-between;align-items:center;'
                'gap:8px;font-size:13px;color:#1F2937"><span>{n}</span>{c}</div>').format(
                n=nombre, a=ayuda, c=chip(valor, nivel))

        nivel_rend = Prod._nivel_rendimiento(r['rend'])
        nivel_oee = self._nivel_oee(r['oee'], r['oee_meta'])
        filas = [
            fila(_("Disponibilidad"), r['disp'], 'na',
                 _("en marcha ÷ (en marcha + paradas)")),
            fila(_("Rendimiento"), r['rend'], nivel_rend,
                 _("piezas al ciclo meta ÷ en marcha")),
            fila(_("Calidad"), r['cal'], 'na', _("buenas ÷ (buenas + averías)")),
        ]
        notas = [_("En marcha %(m)s · paradas %(p)s",
                   m=fmt_horas(c['marcha'] / 60.0), p=fmt_horas(c['parada'] / 60.0))]
        if c['autorizada']:
            notas.append(_("sin paradas autorizadas (%s)", fmt_horas(c['autorizada'] / 60.0)))
        if r['oee_meta']:
            notas.append(_("meta OEE del CT %s %%", fmt(r['oee_meta'])))
        if c['olvidados']:
            notas.append(_("sin %s tramo(s) de más de 12 h: por revisar", c['olvidados']))
        if c['cruzados']:
            notas.append(_("%s tramo(s) cruzados: el tiempo repetido cuenta una vez", c['cruzados']))
        formula = ''
        if r['oee'] is not None:
            formula = "%s × %s × %s = %s" % (pct(r['disp']), pct(r['rend']), pct(r['cal']), pct(r['oee']))
        return Markup(
            '<div style="flex:1 1 220px;min-width:200px;border:1px solid #E5E7EB;background:#FFFFFF;'
            'border-radius:6px;padding:10px 12px;display:flex;flex-direction:column;gap:4px">'
            '<span style="font-size:12px;color:#4B5563">{t1}</span>'
            '<div>{rend}</div>'
            '<span style="font-size:12px;color:#4B5563">{d1}</span>'
            '<div style="border-top:1px solid #E5E7EB;margin:4px 0"></div>'
            '<div style="display:flex;justify-content:space-between;align-items:center">'
            '<span style="font-size:12px;color:#4B5563">{t2}</span>{oee}</div>'
            '{filas}'
            '<span style="font-size:12px;color:#1F2937">{formula}</span>'
            '<span style="font-size:11px;color:#6B7280">{notas}</span></div>'
        ).format(
            t1=_("Rendimiento"), rend=chip(r['rend'], nivel_rend, grande=True),
            d1=_("Tiempo en marcha, sin paradas"),
            t2=_("OEE de la orden"), oee=chip(r['oee'], nivel_oee, grande=True),
            filas=Markup('').join(filas), formula=formula, notas=" · ".join(notas))

    def _avisos_orden(self, r):
        """Mensajes al final de la orden: registros por revisar, orden
        que supera la cantidad y consumo de materia prima por revisar."""
        self.ensure_one()
        Prod = self.env['mrp.workcenter.productivity']
        revisar = Prod._parametro('rendimiento_revisar', 110)
        horas_max = Prod._parametro('horas_max_tramo', 12)
        tolerancia = Prod._parametro('tolerancia_cantidad', 10) / 100.0
        spp = r['spp']
        bloques = []

        detalles = []
        anterior = None
        for linea in self.time_ids.filtered('date_end').sorted('date_start'):
            horas = (linea.date_end - linea.date_start).total_seconds() / 3600.0
            tramo = "%s a %s" % (self._fecha_local(linea.date_start), self._fecha_local(linea.date_end, '%H:%M'))
            # 1.10.0: tramos de esta orden que se cruzan (ya no se bloquean)
            if anterior and linea.date_start < anterior.date_end:
                detalles.append(_(
                    "%(t)s: se cruza con el tramo %(o)s de esta orden; ese tiempo está "
                    "registrado dos veces. Corrige Inicio o Fin de uno de los dos.",
                    t=tramo, o="%s a %s" % (self._fecha_local(anterior.date_start),
                                            self._fecha_local(anterior.date_end, '%H:%M'))))
            if not anterior or linea.date_end > anterior.date_end:
                anterior = linea
            if horas > horas_max:
                detalles.append(_(
                    "%(t)s: el periodo dura %(h)s h, más que un turno (%(m)s h). Revisa Inicio y Fin.",
                    t=tramo, h=fmt(horas, 1), m=fmt(horas_max)))
            valor = linea._calcular_rendimiento()
            piezas = (linea.x_studio_cantidad or 0) + (linea.x_studio_averias or 0)
            if valor is not None and piezas and valor >= revisar:
                esperado = horas * 3600.0 / spp if spp else 0
                detalles.append(_(
                    "%(t)s: %(p)s piezas en %(m)s min = %(r)s %% del estándar (se esperaban %(e)s). "
                    "¿Ciclo desactualizado o cantidad mal digitada?",
                    t=tramo, p=fmt(piezas), m=fmt(horas * 60), r=fmt(valor), e=fmt(esperado)))
        if detalles:
            bloques.append(('revisar', _("%s registro(s) por revisar", len(detalles)), detalles))

        if r['cantidad'] and r['buenas'] > r['cantidad'] * (1 + tolerancia):
            bloques.append(('rojo', _(
                "La orden supera la cantidad programada: %(b)s buenas de %(c)s (%(p)s %%)",
                b=fmt(r['buenas']), c=fmt(r['cantidad']), p=fmt(r['avance'])),
                [_("Si es reposición, déjalo; si no, revisa las cantidades.")]))

        consumo = self._consumo_por_revisar(r['piezas'], tolerancia)
        if consumo:
            bloques.append(('amarillo', _("Consumo de materia prima por revisar"), [
                _("Con %(p)s piezas (buenas + averías) se necesita más de lo trasladado a la orden:",
                  p=fmt(r['piezas']))] + consumo + [
                _("Revisar traslados (Pick Components), devoluciones o cantidades registradas.")]))

        if not bloques:
            return False
        html = Markup('')
        for nivel, titulo, lineas in bloques:
            fondo, texto = COLORES[nivel]
            cuerpo = Markup('').join(Markup('<div>%s</div>') % l for l in lineas)
            html += Markup(
                '<div style="background:{f};color:{c};border-radius:6px;padding:10px 14px;margin-top:8px">'
                '<strong>{t}</strong>{b}</div>').format(f=fondo, c=texto, t=titulo, b=cuerpo)
        return html

    def _consumo_por_revisar(self, piezas, tolerancia):
        """Aviso general de materia prima: requerido = piezas (buenas +
        averías) × cantidad por pieza de la orden, contra lo trasladado
        con Pick Components menos devoluciones (misma base que
        mrp_update_consumed). Solo componentes con algún traslado; en
        órdenes con backorders el trasladado incluye el de todo el grupo,
        así que el aviso puede quedarse corto, nunca sobrar."""
        self.ensure_one()
        mo = self.production_id
        if not mo or not piezas or not mo.product_qty or not mo.procurement_group_id:
            return []
        movimientos = mo.move_raw_ids.filtered(lambda m: m.state != 'cancel')
        if len(mo.workorder_ids) > 1:
            movimientos = movimientos.filtered(lambda m: m.operation_id == self.operation_id)
        if not movimientos:
            return []
        Move = self.env['stock.move'].sudo()
        enviados = Move.search([
            ('group_id', '=', mo.procurement_group_id.id),
            ('state', '=', 'done'),
            ('product_id', 'in', movimientos.product_id.ids),
            ('raw_material_production_id', '=', False),
            ('production_id', '=', False),
            ('picking_id', '!=', False),
            ('origin_returned_move_id', '=', False),
        ])
        if 'consumed' in self.env['stock.picking.type']._fields:
            enviados = enviados.filtered(lambda m: m.picking_id.picking_type_id.consumed)
        else:
            pbm = mo.picking_type_id.warehouse_id.pbm_type_id
            enviados = enviados.filtered(lambda m: m.picking_id.picking_type_id == pbm)
        if not enviados:
            return []
        devueltos = Move.search([
            ('origin_returned_move_id', 'in', enviados.ids), ('state', '=', 'done')])
        avisos = []
        for producto in movimientos.product_id:
            lineas = movimientos.filtered(lambda m: m.product_id == producto)
            uom = lineas[0].product_uom
            requerido = piezas * sum(
                l.product_uom._compute_quantity(l.product_uom_qty, uom) for l in lineas) / mo.product_qty
            def total(movs):
                return sum(m.product_uom._compute_quantity(m.quantity, uom)
                           for m in movs if m.product_id == producto)
            trasladado = total(enviados) - total(devueltos)
            if total(enviados) <= 0:
                continue
            if requerido > trasladado * (1 + tolerancia):
                avisos.append(_(
                    "• %(p)s: requiere %(r)s %(u)s, trasladado %(t)s %(u)s",
                    p=producto.display_name, r=fmt(requerido, 2), t=fmt(trasladado, 2), u=uom.name))
        return avisos
