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
        """Estándar en segundos por pieza, con la misma regla que
        mrp_oee_report: ciclo efectivo del molde (actual, o teórico si
        no hay actual) ÷ cavidades; sin molde, la duración por defecto
        de la operación de la LdM (time_cycle_manual, minutos por
        unidad -- el módulo de moldes la actualiza al aplicar una
        revisión). Eficiencia del CT no aplica.

        El módulo de moldes no es dependencia (producción no lo tiene):
        sus campos se leen solo si existen.
        """
        self.ensure_one()
        if 'mold_id' in self._fields and self.mold_id:
            mold = self.mold_id
            ciclo = mold['cycle_time_effective'] if 'cycle_time_effective' in mold._fields else 0.0
            cavidades = mold['cavity_count'] if 'cavity_count' in mold._fields else 0
            if ciclo and cavidades:
                return ciclo / cavidades
        if self.operation_id and self.operation_id.time_cycle_manual:
            return self.operation_id.time_cycle_manual * 60.0
        return 0.0

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
        """Cifras del panel. Rendimiento y ritmo solo con los tramos
        cerrados que tienen piezas (los setups y paradas no se miden)."""
        self.ensure_one()
        lineas = self.time_ids
        buenas = sum(lineas.mapped('x_studio_cantidad'))
        averias = sum(lineas.mapped('x_studio_averias'))
        produccion = lineas.filtered(lambda l: l.date_end and l.date_start and (
            (l.x_studio_cantidad or 0) + (l.x_studio_averias or 0)) > 0)
        segundos_prod = sum(
            (l.date_end - l.date_start).total_seconds() for l in produccion)
        piezas_prod = sum(produccion.mapped('x_studio_cantidad')) + sum(
            produccion.mapped('x_studio_averias'))
        buenas_prod = sum(produccion.mapped('x_studio_cantidad'))
        spp = self._averia_segundos_por_pieza()
        cantidad = self.qty_production or 0.0
        rend = (piezas_prod * spp / segundos_prod * 100.0) if spp and segundos_prod else None
        faltan = max(cantidad - buenas, 0.0)
        horas_ritmo = (faltan / (buenas_prod / segundos_prod) / 3600.0
                       if buenas_prod and segundos_prod else None)
        horas_std = faltan * spp / 3600.0 if spp else None
        # Proyección contra la DURACIÓN planeada, no contra fechas: Odoo
        # sobrescribe las fechas de la OT al pulsar Iniciar o Marcar como
        # hecha y no guarda las originales (decisión 17-11, opción B).
        horas = horas_ritmo if horas_ritmo is not None else horas_std
        planeada = self.duration_expected or 0.0
        registrada = sum(
            (l.date_end - l.date_start).total_seconds() / 60.0
            for l in lineas if l.date_start and l.date_end)
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
            'diferencia': diferencia, 'fin_estimado': fin_estimado,
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
                 'time_ids.date_start', 'time_ids.date_end', 'qty_production',
                 'duration_expected')
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
            if r['rend'] is not None:
                tarjetas.append(wo._tarjeta(
                    _("Rendimiento promedio"), "%s %%" % fmt(r['rend']),
                    _("Solo tramos con producción"),
                    Prod._nivel_rendimiento(r['rend'])))
            if r['spp']:
                tarjetas.append(wo._tarjeta(
                    _("Ciclo efectivo"), _("%s s / pieza", fmt(r['spp'], 1)),
                    _("Ciclo ÷ cavidades · %s piezas/h", fmt(3600.0 / r['spp']))))
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
            tarjetas.append(wo._tarjeta(_("Proyección"), etiqueta, " · ".join(partes), nivel))
            wo.panel_avance_html = Markup(
                '<div style="display:flex;flex-wrap:wrap;gap:12px">%s</div>') % Markup('').join(tarjetas)
            wo.avisos_html = wo._avisos_orden(r) or False

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
        for linea in self.time_ids.filtered('date_end').sorted('date_start'):
            horas = (linea.date_end - linea.date_start).total_seconds() / 3600.0
            tramo = "%s a %s" % (self._fecha_local(linea.date_start), self._fecha_local(linea.date_end, '%H:%M'))
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
