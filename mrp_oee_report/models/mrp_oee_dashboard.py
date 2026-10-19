# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

from .oee_sql import column_exists

_logger = logging.getLogger(__name__)

MEASURES = (
    'min_registrado', 'min_operando', 'min_operando_std', 'min_autorizada',
    'min_no_programada', 'unidades_buenas', 'unidades_averias',
    'min_estandar', 'min_valioso', 'eventos_parada', 'microparadas',
)
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
            },
            'eventos': int(m['eventos_parada']),
            'microparadas': int(m['microparadas']),
        }

    def _status(self, value, target):
        if value is None:
            return 'none'
        target = target or DEFAULT_TARGET
        if value >= target:
            return 'good'
        if value >= target - YELLOW_BAND:
            return 'warn'
        return 'bad'

    # ------------------------------------------------------------------
    # Duración de turnos según calendario (para "Sin registrar")
    # ------------------------------------------------------------------
    def _calendar_minutes(self):
        cr = self.env.cr
        where = ['TRUE']
        if column_exists(cr, 'resource_calendar_attendance', 'display_type'):
            where.append('display_type IS NULL')
        if column_exists(cr, 'resource_calendar_attendance', 'resource_id'):
            where.append('resource_id IS NULL')
        wt = ('week_type' if column_exists(cr, 'resource_calendar_attendance',
                                           'week_type') else "''")
        cr.execute("""
            SELECT calendar_id, name, %s, SUM(hour_to - hour_from) * 60
              FROM resource_calendar_attendance
             WHERE %s
          GROUP BY calendar_id, name, %s
        """ % (wt, ' AND '.join(where), wt))
        out = {}
        for cal, name, _w, minutes in cr.fetchall():
            key = (cal, name)
            out[key] = max(out.get(key, 0.0), minutes or 0.0)
        return out

    def _shift_time(self, domain):
        rows = self._agg(domain, ('workcenter_id', 'shift_date:day', 'shift_name'))
        cal = self._calendar_minutes()
        turno = registrado = sin_reg = 0.0
        known = 0
        for (wc, _day, sname), m in rows:
            minutes = cal.get((wc.resource_calendar_id.id, sname)) if sname else None
            if minutes:
                known += 1
                turno += minutes
                registrado += m['min_registrado']
                sin_reg += max(minutes - m['min_registrado'], 0.0)
        return {'turnos': len(rows), 'turnos_con_calendario': known,
                'min_turno': turno, 'min_sin_registrar': sin_reg}

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
    def _defects(self, df, dt, wc_ids):
        if 'mrp.averia.report' not in self.env:
            return {'available': False, 'rows': []}
        Model = self.env['mrp.averia.report']
        fg = Model.fields_get(attributes=['type', 'relation', 'store'])
        def pick(cond):
            for name, f in fg.items():
                if cond(name, f):
                    return name
            return None
        group = pick(lambda n, f: f['type'] in ('many2one', 'selection', 'char')
                     and any(k in n for k in ('tipo', 'defect', 'categor', 'causa')))
        qty = pick(lambda n, f: f['type'] in ('integer', 'float')
                   and 'buena' not in n and any(k in n for k in ('averia', 'cantidad')))
        date_f = pick(lambda n, f: f['type'] in ('date', 'datetime')
                      and any(k in n for k in ('fecha', 'date')))
        wc_f = pick(lambda n, f: f['type'] == 'many2one'
                    and f.get('relation') == 'mrp.workcenter')
        if not (group and qty):
            return {'available': False, 'rows': [],
                    'note': 'No se identificaron los campos de tipo y cantidad.'}
        dom = []
        if date_f:
            dom += [(date_f, '>=', df), (date_f, '<', dt + timedelta(days=1))]
        if wc_f and wc_ids is not None:
            dom.append((wc_f, 'in', wc_ids))
        try:
            rows = Model._read_group(dom, [group], ['%s:sum' % qty])
        except Exception:  # noqa: BLE001 - informe opcional
            _logger.exception('Pareto de defectos: no se pudo agrupar')
            return {'available': False, 'rows': []}
        out = []
        for key, total in rows:
            label = key.display_name if hasattr(key, 'display_name') else key
            if total:
                out.append({'label': label or 'Sin tipo', 'value': total})
        return {'available': True, 'rows': self._pareto(out)}

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
        kpi.update(self._shift_time(domain))

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
            'defects': self._defects(df, dt, wc_ids),
            'warnings': warnings,
            'domain': domain,
            'options': {
                'tags': [{'id': t.id, 'name': t.name} for t in Tag.search([])],
                'workcenters': [{'id': w.id, 'name': w.name, 'code': w.code or '',
                                 'tag_ids': w.tag_ids.ids} for w in wcs],
                'shifts': shift_opts,
            },
        }
