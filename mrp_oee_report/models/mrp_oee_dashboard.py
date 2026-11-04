# -*- coding: utf-8 -*-
import logging
import re
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

from .oee_sql import windows_sql

_logger = logging.getLogger(__name__)

MEASURES = (
    'min_registrado', 'min_operando', 'min_operando_std', 'min_autorizada',
    'min_no_programada', 'unidades_buenas', 'unidades_averias',
    'min_estandar', 'min_valioso', 'eventos_parada', 'microparadas',
    'min_traslape',
)
LABEL_RE = re.compile(r'Turno ?[0-9]+')
GAP_MINUTES = 30          # turno con más de esto sin registro va a revisión
YELLOW_BAND = 10.0          # puntos bajo la meta que siguen en amarillo
DEFAULT_TARGET = 75.0       # si el CT no tiene meta
MAX_ROWS = 300


def _pct(num, den):
    return round(100.0 * num / den, 1) if den else None


class MrpOeeDashboard(models.AbstractModel):
    _name = 'mrp.oee.dashboard'
    _description = 'Tablero OEE (datos)'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _tz(self):
        return pytz.timezone(self.env.user.tz or 'America/Bogota')

    def _range(self, params):
        today = fields.Date.context_today(self)
        rng = params.get('range') or 'today'
        if rng == 'yesterday':
            return today - timedelta(days=1), today - timedelta(days=1)
        if rng == '7d':
            return today - timedelta(days=6), today
        if rng == '30d':
            return today - timedelta(days=29), today
        if rng == 'month':
            return today.replace(day=1), today
        if rng == 'custom':
            df = fields.Date.to_date(params.get('date_from')) or today
            dt = fields.Date.to_date(params.get('date_to')) or df
            return min(df, dt), max(df, dt)
        return today, today

    def _workcenter_ids(self, params):
        if params.get('workcenter_ids'):
            return [int(x) for x in params['workcenter_ids']]
        if params.get('tag_ids'):
            return self.env['mrp.workcenter'].search(
                [('tag_ids', 'in', [int(x) for x in params['tag_ids']])]).ids
        return None

    def _domain(self, params, df, dt, with_shift=True):
        dom = [('shift_date', '>=', df), ('shift_date', '<=', dt)]
        wc_ids = self._workcenter_ids(params)
        if wc_ids is not None:
            dom.append(('workcenter_id', 'in', wc_ids))
        if with_shift and params.get('shift'):
            dom.append(('shift_label', '=', params['shift']))
        if params.get('planned_only'):
            dom.append(('shift_is_planned', '=', True))
        s = (params.get('search') or '').strip()
        if s:
            dom += ['|', '|', '|',
                    ('production_id.name', 'ilike', s),
                    ('product_id.name', 'ilike', s),
                    ('product_id.default_code', 'ilike', s),
                    ('operario', 'ilike', s)]
        return dom

    def _agg(self, domain, groupby=()):
        Line = self.env['mrp.oee.line']
        rows = Line._read_group(domain, list(groupby),
                                ['%s:sum' % m for m in MEASURES])
        out = []
        n = len(groupby)
        for row in rows:
            vals = dict(zip(MEASURES, [v or 0.0 for v in row[n:]]))
            out.append((row[:n], vals))
        return out

    def _metrics(self, m, target=None):
        cargado = m['min_operando'] + m['min_no_programada']
        d = _pct(m['min_operando'], cargado)
        r = _pct(m['min_estandar'], m['min_operando_std'])
        c = _pct(m['unidades_buenas'], m['unidades_buenas'] + m['unidades_averias'])
        oee = round(d * r * c / 10000.0, 1) if None not in (d, r, c) else None
        vel = m['min_operando_std'] - m['min_estandar']
        cal = m['min_estandar'] - m['min_valioso']
        lost = m['min_no_programada'] + max(vel, 0.0) + cal
        return {
            'oee': oee, 'd': d, 'r': r, 'c': c,
            'target': target,
            'status': self._status(oee, target),
            'buenas': round(m['unidades_buenas']),
            'averias': round(m['unidades_averias']),
            'scrap_rate': _pct(m['unidades_averias'],
                               m['unidades_buenas'] + m['unidades_averias']),
            'min': {
                'registrado': m['min_registrado'],
                'autorizada': m['min_autorizada'],
                'cargado': cargado,
                'no_programada': m['min_no_programada'],
                'operando': m['min_operando'],
                'sin_estandar': m['min_operando'] - m['min_operando_std'],
                'velocidad': vel,
                'calidad': cal,
                'valioso': m['min_valioso'],
                'perdido': lost,
                'traslape': m.get('min_traslape', 0.0),
            },
            'eventos': int(m['eventos_parada']),
            'microparadas': int(m['microparadas']),
        }

    def _status(self, value, target):
        if value is None:
            return 'none'
        if value > 100.5:
            return 'check'      # OEE sobre 100%: imposible, es un dato a revisar
        target = target or DEFAULT_TARGET
        if value >= target:
            return 'good'
        if value >= target - YELLOW_BAND:
            return 'warn'
        return 'bad'

    # ------------------------------------------------------------------
    # Duración de turnos según calendario (misma regla de mrp_shift_resolver)
    # ------------------------------------------------------------------
    def _windows(self, cal_ids, df, dt):
        if not cal_ids:
            return []
        sql = windows_sql(self.env.cr, '%(df)s', '%(dt)s', 'rc.id IN %(cals)s')
        self.env.cr.execute(
            'SELECT calendar_id, shift_name, shift_date, planned, ws, we FROM ('
            + sql + ') w WHERE w.shift_date BETWEEN %(df)s AND %(dt)s',
            {'df': df - timedelta(days=1), 'dt': dt + timedelta(days=1),
             'cals': tuple(cal_ids)})
        return [r for r in self.env.cr.fetchall() if df <= r[2] <= dt]

    def _shift_time(self, domain, params, df, dt):
        """Minutos de turno planeados (calendario, sin franjas "Descanso"),
        solo hasta ahora, para las máquinas con registro en el filtro.
        Devuelve además los turnos con hueco de registro (para revisión)."""
        label = params.get('shift') or False
        now = fields.Datetime.now()
        by_shift = {}
        for (wc, day, sname), m in self._agg(
                domain, ('workcenter_id', 'shift_date:day', 'shift_name')):
            by_shift[(wc.id, day, sname)] = m['min_registrado']
        if (params.get('search') or '').strip():
            # Filtrando una OP, producto u operario, los turnos completos de la
            # máquina no son su base: la base es su propio tiempo registrado.
            total = sum(by_shift.values())
            return {'min_turno': 0.0, 'min_extra': 0.0, 'min_sin_registrar': 0.0,
                    'min_base': total, 'base_registro': True}, []
        wcs = self.env['mrp.workcenter'].browse({k[0] for k in by_shift})
        cal_wcs = {}
        for wc in wcs:
            if wc.resource_calendar_id:
                cal_wcs.setdefault(wc.resource_calendar_id.id, []).append(wc)
        planned = {}
        for cal_id, sname, sdate, is_planned, ws, we in self._windows(set(cal_wcs), df, dt):
            if not is_planned:
                continue
            m = LABEL_RE.search(sname or '')
            if label and (m.group(0) if m else sname) != label:
                continue
            minutes = max((min(we, now) - ws).total_seconds() / 60.0, 0.0)
            if not minutes:
                continue
            for wc in cal_wcs[cal_id]:
                key = (wc.id, sdate, sname)
                planned[key] = planned.get(key, 0.0) + minutes
        turno = sum(planned.values())
        reg_planned = sum(v for k, v in by_shift.items() if k in planned)
        extra = sum(v for k, v in by_shift.items() if k not in planned)
        gaps = []
        for (wc_id, sdate, sname), minutes in planned.items():
            reg = by_shift.get((wc_id, sdate, sname), 0.0)
            if minutes - reg > GAP_MINUTES:
                gaps.append({'workcenter_id': wc_id, 'workcenter': self.env['mrp.workcenter'].browse(wc_id).display_name,
                             'day': fields.Date.to_string(sdate), 'shift': sname,
                             'turno': minutes, 'registrado': reg, 'hueco': minutes - reg})
        gaps.sort(key=lambda g: -g['hueco'])
        return {
            'min_turno': turno,
            'min_extra': extra,
            'min_sin_registrar': max(turno - reg_planned, 0.0),
            'min_base': turno + extra,
            'base_registro': False,
        }, gaps[:200]

    # ------------------------------------------------------------------
    # Plan vs real
    # ------------------------------------------------------------------
    def _planned_qty(self, params, df, dt):
        tz = self._tz()
        start = tz.localize(datetime.combine(df, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        end = tz.localize(datetime.combine(dt + timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        dom = [('state', '!=', 'cancel'),
               ('date_start', '!=', False), ('date_finished', '!=', False),
               ('date_start', '<', end), ('date_finished', '>', start)]
        wc_ids = self._workcenter_ids(params)
        if wc_ids is not None:
            dom.append(('workcenter_id', 'in', wc_ids))
        s = (params.get('search') or '').strip()
        if s:
            dom += ['|', '|', ('production_id.name', 'ilike', s),
                    ('product_id.name', 'ilike', s),
                    ('product_id.default_code', 'ilike', s)]
        by_wc = {}
        for wo in self.env['mrp.workorder'].search(dom):
            total = (wo.date_finished - wo.date_start).total_seconds()
            if total <= 0:
                continue
            ov = (min(wo.date_finished, end) - max(wo.date_start, start)).total_seconds()
            if ov <= 0:
                continue
            by_wc[wo.workcenter_id.id] = by_wc.get(wo.workcenter_id.id, 0.0) \
                + wo.qty_production * ov / total
        return by_wc

    # ------------------------------------------------------------------
    # Pareto de defectos (tipificación de averías, si está instalada)
    # ------------------------------------------------------------------
    def _defects(self, params, df, dt):
        """Pareto de piezas no conformes desde la tipificación de averías
        (mrp.averia.report), con los MISMOS filtros del tablero."""
        if 'mrp.averia.report' not in self.env:
            return {'available': False, 'rows': []}
        Model = self.env['mrp.averia.report']
        flds = Model._fields
        need = ('categoria_id', 'cantidad')
        if any(f not in flds for f in need):
            return {'available': False, 'rows': [],
                    'note': 'La tipificación no tiene categoría y cantidad.'}
        dom = []
        if 'shift_date' in flds:
            dom += [('shift_date', '>=', df), ('shift_date', '<=', dt)]
        elif 'fecha' in flds:
            dom += [('fecha', '>=', df), ('fecha', '<', dt + timedelta(days=1))]
        wc_ids = self._workcenter_ids(params)
        if wc_ids is not None and 'workcenter_id' in flds:
            dom.append(('workcenter_id', 'in', wc_ids))
        if params.get('shift') and 'shift_name' in flds:
            dom.append(('shift_name', 'ilike', params['shift']))
        s = (params.get('search') or '').strip()
        if s:
            terms = []
            if 'production_id' in flds:
                terms.append(('production_id.name', 'ilike', s))
            if 'product_id' in flds:
                terms += [('product_id.name', 'ilike', s),
                          ('product_id.default_code', 'ilike', s)]
            if terms:
                dom += ['|'] * (len(terms) - 1) + terms
        try:
            rows = Model._read_group(dom, ['categoria_id'], ['cantidad:sum'])
        except Exception:  # noqa: BLE001 - informe opcional
            _logger.exception('Pareto de defectos: no se pudo agrupar')
            return {'available': False, 'rows': []}
        out = [{'label': cat.display_name if cat else 'Sin categoría', 'value': total}
               for cat, total in rows if total]
        return {'available': True, 'rows': self._pareto(out), 'domain': dom}

    @api.model
    def _pareto(self, rows):
        rows = sorted(rows, key=lambda r: -r['value'])
        total = sum(r['value'] for r in rows) or 1.0
        acc = 0.0
        for r in rows:
            acc += r['value']
            r['cum'] = round(100.0 * acc / total, 1)
            r['share'] = round(100.0 * r['value'] / total, 1)
        return rows

    # ------------------------------------------------------------------
    # Calidad del registro
    # ------------------------------------------------------------------
    @api.model
    def _hhmm(self, minutes):
        minutes = int(round(minutes or 0))
        return '%d:%02d h' % (minutes // 60, minutes % 60)

    def _review(self, domain, gaps):
        Line = self.env['mrp.oee.line']
        # Domain sin el filtro de turno planeado: las olvidadas no tienen tiempo
        olv = Line.search_read(
            domain + [('olvidada', '=', True), ('es_primera', '=', True)],
            ['productivity_id', 'workcenter_id', 'production_id', 'operario',
             'date_start', 'min_bruto', 'loss_id', 'unidades_linea', 'shift_name'],
            order='min_bruto desc', limit=200)
        tras = []
        for (wc, day, sname), m in self._agg(
                domain + [('min_traslape', '>', 0.5)],
                ('workcenter_id', 'shift_date:day', 'shift_name')):
            ops = Line.search_read(
                domain + [('workcenter_id', '=', wc.id), ('shift_date', '=', day),
                          ('shift_name', '=', sname), ('min_traslape', '>', 0.5)],
                ['production_id'])
            names = sorted({o['production_id'][1] for o in ops if o['production_id']})
            tras.append({'workcenter_id': wc.id, 'workcenter': wc.display_name,
                         'day': fields.Date.to_string(day), 'shift': sname,
                         'minutos': m['min_traslape'], 'ordenes': ', '.join(names)})
        tras.sort(key=lambda r: -r['minutos'])
        ordenes = []
        rows = Line._read_group(
            domain + [('production_id', '!=', False)], ['production_id'],
            ['unidades_linea:sum', 'min_operando:sum', 'min_operando_std:sum',
             'min_estandar:sum'])
        for prod, unidades, op, op_std, std in rows:
            unidades = unidades or 0.0
            r = (100.0 * std / op_std) if op_std else None
            reg_pct = (100.0 * unidades / prod.qty_produced) if prod.qty_produced else None
            motivos = []
            if prod.state == 'done' and reg_pct is not None and reg_pct < 90:
                motivos.append('Producción registrada %d%% de lo producido' % reg_pct)
            if r is not None and r > 105:
                motivos.append('Rendimiento %d%%: revisar ciclo o cantidades' % r)
            if (op or 0) > 30 and not unidades:
                motivos.append('%s operando sin piezas registradas' % self._hhmm(op))
            if motivos:
                ordenes.append({'production_id': prod.id, 'name': prod.name,
                                'product': prod.product_id.display_name,
                                'registradas': unidades, 'producidas': prod.qty_produced,
                                'r': round(r) if r is not None else None,
                                'motivos': ' · '.join(motivos)})
        return {
            'olvidadas': [{'productivity_id': o['productivity_id'] and o['productivity_id'][0],
                           'workcenter': o['workcenter_id'] and o['workcenter_id'][1],
                           'orden': o['production_id'] and o['production_id'][1],
                           'operario': o['operario'],
                           'inicio': fields.Datetime.context_timestamp(
                               self, o['date_start']).strftime('%d/%m/%Y %H:%M'),
                           'turno': o['shift_name'], 'motivo': o['loss_id'] and o['loss_id'][1],
                           'minutos': o['min_bruto'], 'unidades': o['unidades_linea']}
                          for o in olv],
            'traslapes': tras[:200],
            'huecos': gaps,
            'ordenes': ordenes[:200],
        }

    @api.model
    def refresh_and_get(self, params=None):
        """Botón Actualizar: recalcula solo los últimos días."""
        self.env['mrp.oee.line'].sudo().recompute_recent()
        return self.get_dashboard_data(params)

    @api.model
    def recompute_period_and_get(self, params=None):
        """Botón Recalcular periodo: rehace las fechas filtradas (máx. 13 meses
        por clic) para reflejar correcciones antiguas."""
        params = params or {}
        df, dt = self._range(params)
        df = max(df, dt - timedelta(days=400))
        self.env['mrp.oee.line'].sudo().recompute_period(df, dt)
        return self.get_dashboard_data(params)

    # ------------------------------------------------------------------
    # Punto de entrada
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, params=None):
        params = params or {}
        df, dt = self._range(params)
        domain = self._domain(params, df, dt)
        wc_ids = self._workcenter_ids(params)

        # --- por máquina (base de meta ponderada y costo) ---
        machines = []
        tot_target_w = tot_cargado = cost_lost = 0.0
        plan = self._planned_qty(params, df, dt) if not params.get('shift') else None
        for (wc,), m in self._agg(domain, ('workcenter_id',)):
            target = wc.oee_target or DEFAULT_TARGET
            met = self._metrics(m, target)
            cargado = met['min']['cargado']
            tot_target_w += target * cargado
            tot_cargado += cargado
            cost = met['min']['perdido'] / 60.0 * (wc.costs_hour or 0.0)
            cost_lost += cost
            groups = [t.name for t in wc.tag_ids if not t.name.upper().startswith('UN')]
            p = plan.get(wc.id) if plan is not None else None
            met.update({
                'id': wc.id, 'code': wc.code or wc.name, 'name': wc.name,
                'group': groups[0] if groups else '',
                'cost_lost': round(cost),
                'plan': round(p) if p else None,
                'cumplimiento': _pct(met['buenas'], p) if p else None,
            })
            machines.append(met)
        plant_target = round(tot_target_w / tot_cargado, 1) if tot_cargado else DEFAULT_TARGET

        total = self._agg(domain)
        kpi = self._metrics(total[0][1] if total else dict.fromkeys(MEASURES, 0.0),
                            plant_target)
        kpi['cost_lost'] = round(cost_lost)
        shift_time, gaps = self._shift_time(domain, params, df, dt)
        kpi.update(shift_time)

        # --- plan vs real ---
        plan_total = sum(plan.values()) if plan else 0.0
        kpi['plan'] = {
            'available': plan is not None,
            'planificado': round(plan_total),
            'conforme': kpi['buenas'],
            'cumplimiento': _pct(kpi['buenas'], plan_total) if plan_total else None,
            'note': ('El plan no se separa por turno: quite el filtro de turno.'
                     if plan is None else
                     'Prorrateado de las órdenes de trabajo programadas en el periodo.'),
        }

        # --- narrativa: mayor pérdida ---
        mins = kpi['min']
        losses = [('paradas no programadas', mins['no_programada']),
                  ('correr por debajo del estándar', max(mins['velocidad'], 0.0)),
                  ('averías (calidad)', mins['calidad'])]
        name, lost = max(losses, key=lambda x: x[1])
        per_unit = (mins['valioso'] / kpi['buenas']) if kpi['buenas'] else 0.0
        kpi['narrative'] = {
            'reason': name, 'minutes': lost,
            'units': round(lost / per_unit) if per_unit else None,
        } if lost > 0 else None

        # --- turnos ---
        days = (dt - df).days + 1
        if days <= 7:
            shift_rows = self._agg(domain, ('shift_date:day', 'shift_label'))
            shifts = [{'label': '%s %s' % (d.strftime('%d/%m'), lbl or ''),
                       'day': fields.Date.to_string(d), 'shift': lbl,
                       **self._metrics(m, plant_target)}
                      for (d, lbl), m in shift_rows]
            shifts.sort(key=lambda r: (r['day'], r['shift'] or ''))
            shift_mode = 'shift'
        else:
            shift_rows = self._agg(domain, ('shift_date:day',))
            shifts = [{'label': d.strftime('%d/%m'), 'day': fields.Date.to_string(d),
                       **self._metrics(m, plant_target)} for (d,), m in shift_rows]
            shifts.sort(key=lambda r: r['day'])
            shift_mode = 'day'

        # --- pestañas ---
        def tab(groupby, label_fn):
            rows = []
            for key, m in self._agg(domain, (groupby,)):
                k = key[0]
                if not k:
                    continue
                met = self._metrics(m, plant_target)
                met['id'] = k.id if hasattr(k, 'id') else k
                met['name'] = label_fn(k)
                rows.append(met)
            rows.sort(key=lambda r: -r['min']['registrado'])
            return rows[:MAX_ROWS]
        orders = tab('production_id', lambda r: r.name)
        products = tab('product_id', lambda r: r.display_name)
        operators = tab('operario', lambda r: r)

        # --- Paretos de paradas ---
        def stops(cls):
            out = []
            for (loss,), m in self._agg(domain + [('time_class', '=', cls)], ('loss_id',)):
                out.append({'label': loss.name or 'Sin motivo',
                            'value': m['min_registrado'],
                            'events': int(m['eventos_parada']),
                            'micro': int(m['microparadas'])})
            return self._pareto(out)

        # --- avisos ---
        review_cache = self._review(domain, gaps)
        warnings = []
        if mins['sin_estandar'] > 1:
            warnings.append('%d min operando sin ciclo estándar (sin molde ni ciclo '
                            'manual): no entran al Rendimiento.' % mins['sin_estandar'])
        over = [x['code'] for x in machines if (x['r'] or 0) > 105]
        if over:
            warnings.append('Rendimiento sobre 105%% en %s: revisar ciclo estándar o '
                            'cantidades reportadas.' % ', '.join(over[:8]))
        if not self.env['mrp.workcenter.productivity.loss'].search_count(
                [('oee_authorized_stop', '=', True)]):
            warnings.append('Ningún motivo de pérdida está marcado como parada '
                            'autorizada: setup y purga restan Disponibilidad.')
        if kpi['min_turno'] and kpi['min_sin_registrar'] > 0.05 * kpi['min_turno']:
            warnings.append('%d%% del tiempo de turno no tiene registro de tiempo.'
                            % round(100 * kpi['min_sin_registrar'] / kpi['min_turno']))
        n_olv = len(review_cache['olvidadas'])
        if n_olv:
            warnings.append('%d línea(s) de más de 12 h no cuentan en el OEE '
                            '(ver Calidad del registro).' % n_olv)
        if mins.get('traslape', 0) > 1:
            warnings.append('%s de tiempo traslapado en la misma máquina se contó una '
                            'sola vez (ver Calidad del registro).'
                            % self._hhmm(mins['traslape']))

        # --- opciones de filtros ---
        Tag = self.env['mrp.workcenter.tag']
        wcs = self.env['mrp.workcenter'].search([])
        shift_opts = sorted({lbl for (lbl,), _m in self._agg(
            self._domain(dict(params, shift=False), df - timedelta(days=30), dt,
                         with_shift=False), ('shift_label',)) if lbl})

        return {
            'range': {'from': fields.Date.to_string(df), 'to': fields.Date.to_string(dt),
                      'days': days},
            'kpi': kpi,
            'machines': sorted(machines, key=lambda r: -r['min']['perdido']),
            'shifts': shifts, 'shift_mode': shift_mode,
            'tabs': {'orders': orders, 'products': products, 'operators': operators},
            'stops_unplanned': stops('unplanned'),
            'stops_authorized': stops('authorized'),
            'defects': self._defects(params, df, dt),
            'review': review_cache,
            'last_refresh': self.env['ir.config_parameter'].sudo().get_param(
                'mrp_oee_report.last_refresh') or False,
            'rebuild': self.env['mrp.oee.line'].sudo().rebuild_status(),
            'recalc_days': self.env['mrp.oee.line'].sudo()._recalc_days(),
            'warnings': warnings,
            'domain': domain,
            'options': {
                'tags': [{'id': t.id, 'name': t.name} for t in Tag.search([])],
                'workcenters': [{'id': w.id, 'name': w.name, 'code': w.code or '',
                                 'tag_ids': w.tag_ids.ids} for w in wcs],
                'shifts': shift_opts,
            },
        }
