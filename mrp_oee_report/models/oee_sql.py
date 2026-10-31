# -*- coding: utf-8 -*-
"""SQL común del OEE (v1.2): una fila por TRAMO de línea de tiempo dentro de un
turno del calendario.

Reglas de tiempo (acordadas con planta, 21/10/2026):

1. Cada línea de seguimiento de tiempo se reparte entre los turnos del
   calendario del centro de trabajo que atraviesa (los avances van de 10 a
   80 min y cruzan el cambio de turno). Minutos y unidades se reparten en la
   misma proporción. El turno se identifica por el NOMBRE de la línea de
   asistencia, como en mrp_shift_resolver; un turno partido por medianoche se
   asigna a la fecha en que arrancó.
2. Una línea de más de ``FORGOTTEN_HOURS`` horas es un registro olvidado: no
   cuenta en el OEE (ni tiempo ni unidades) y se lista en Calidad del registro.
3. El reloj de la máquina se cuenta una vez: si dos tramos se traslapan en el
   mismo centro de trabajo, cada minuto se asigna a UNA línea (parada no
   programada > parada autorizada > operando; empate: la más reciente). No se
   aplica en los centros con una etiqueta listada en el parámetro
   ``mrp_oee_report.parallel_tags`` (por defecto "Terminado & Empaque").
4. Estándar por pieza: ciclo ACTUAL del molde; si está vacío, el teórico;
   sin molde, time_cycle_manual de la operación. La eficiencia de tiempo del CT
   no se aplica.

Modelo de minutos:
    registrado = operando + autorizada + no_programada
    cargado    = registrado - autorizada
    D = operando / cargado
    R = estándar de lo producido / operando con estándar
    C = buenas / (buenas + averías)

Compatible Odoo 18 y 19: la categoría se lee de la tabla de tipos de pérdida;
columnas opcionales (turnos, moldes, operario, vigencias) se detectan antes.
"""
import logging

_logger = logging.getLogger(__name__)

MICROSTOP_MINUTES = 5.0
FORGOTTEN_HOURS = 12
FALLBACK_TZ = 'America/Bogota'
PARALLEL_PARAM = 'mrp_oee_report.parallel_tags'
PARALLEL_DEFAULT = 'Terminado & Empaque'


def column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s", (table, column))
    return bool(cr.fetchone())


def table_exists(cr, table):
    cr.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        (table,))
    return bool(cr.fetchone())


def drop_relation(cr, name):
    """Elimina una vista normal o materializada, la que exista."""
    cr.execute("SELECT relkind FROM pg_class WHERE relname = %s", (name,))
    row = cr.fetchone()
    if not row:
        return
    if row[0] == 'm':
        cr.execute('DROP MATERIALIZED VIEW IF EXISTS %s CASCADE' % name)
    elif row[0] == 'v':
        cr.execute('DROP VIEW IF EXISTS %s CASCADE' % name)


def attendance_filters(cr, alias, date_expr):
    """Condiciones de vigencia de una línea de asistencia en una fecha."""
    A = 'resource_calendar_attendance'
    out = []
    if column_exists(cr, A, 'date_from'):
        out.append('(%s.date_from IS NULL OR %s.date_from <= %s)' % (alias, alias, date_expr))
    if column_exists(cr, A, 'date_to'):
        out.append('(%s.date_to IS NULL OR %s.date_to >= %s)' % (alias, alias, date_expr))
    if column_exists(cr, A, 'display_type'):
        out.append('%s.display_type IS NULL' % alias)
    if column_exists(cr, A, 'resource_id'):
        out.append('%s.resource_id IS NULL' % alias)
    return (' AND ' + ' AND '.join(out)) if out else ''


def windows_sql(cr, date_from_expr, date_to_expr, calendar_filter='TRUE'):
    """Ventanas de turno en UTC para cada calendario y fecha.

    Columnas: calendar_id, shift_name, shift_date, planned, ws, we.
    Una línea de asistencia que empieza a las 00:00 y cuyo turno tiene otra
    línea que termina a las 24:00 es la continuación de medianoche: su fecha
    operativa es el día anterior (misma regla que mrp_shift_resolver).
    planned = False si la franja es "Descanso" (day_period = 'lunch').
    """
    filt = attendance_filters(cr, 'a', 'g.dd::date')
    return """
        SELECT rc.id AS calendar_id,
               a.name AS shift_name,
               CASE WHEN a.hour_from = 0 AND EXISTS (
                        SELECT 1 FROM resource_calendar_attendance a2
                         WHERE a2.calendar_id = a.calendar_id
                           AND a2.name = a.name AND a2.hour_to >= 24)
                    THEN g.dd::date - 1 ELSE g.dd::date END AS shift_date,
               (a.day_period IS DISTINCT FROM 'lunch') AS planned,
               ((g.dd::date + a.hour_from * INTERVAL '1 hour')
                    AT TIME ZONE COALESCE(rc.tz, '{tz}')) AT TIME ZONE 'UTC' AS ws,
               ((g.dd::date + a.hour_to * INTERVAL '1 hour')
                    AT TIME ZONE COALESCE(rc.tz, '{tz}')) AT TIME ZONE 'UTC' AS we
          FROM resource_calendar rc
          JOIN resource_calendar_attendance a ON a.calendar_id = rc.id
          CROSS JOIN generate_series(({df})::date, ({dt})::date,
                                     INTERVAL '1 day') AS g(dd)
         WHERE a.dayofweek = (EXTRACT(ISODOW FROM g.dd)::int - 1)::varchar
           AND a.hour_to > a.hour_from
           AND {cal} {filt}
    """.format(tz=FALLBACK_TZ, df=date_from_expr, dt=date_to_expr,
               cal=calendar_filter, filt=filt)


# Columnas que produce build_line_sql, en orden (las de la tabla mrp_oee_line).
OUT_COLS = (
    'id', 'productivity_id', 'es_primera', 'workcenter_id', 'company_id',
    'shift_date', 'shift_name', 'shift_label', 'shift_is_planned', 'date_start',
    'workorder_id', 'production_id', 'product_id', 'operario', 'loss_id',
    'loss_type', 'authorized_stop', 'time_class', 'std_source', 'std_min_unit',
    'paralelo', 'olvidada', 'min_bruto', 'min_traslape', 'min_registrado',
    'min_operando', 'min_operando_std', 'min_autorizada', 'min_no_programada',
    'unidades_buenas', 'unidades_averias', 'unidades_linea', 'min_estandar',
    'min_valioso', 'eventos_parada', 'microparadas', 'costs_hour', 'oee_target',
)


def build_line_sql(cr):
    """SELECT de los tramos con shift_date entre %(df)s y %(dt)s (parámetros
    de psycopg2). Se usa para recalcular un rango de fechas en la tabla."""
    P = 'mrp_workcenter_productivity'
    warnings = []

    # ---------------- turno propio (respaldo si no hay calendario) ----------
    if column_exists(cr, P, 'shift_date'):
        own_date = ("COALESCE(p.shift_date, (p.date_start AT TIME ZONE 'UTC' "
                    "AT TIME ZONE '%s')::date)" % FALLBACK_TZ)
    else:
        own_date = ("(p.date_start AT TIME ZONE 'UTC' AT TIME ZONE '%s')::date"
                    % FALLBACK_TZ)
    own_name = 'p.shift_name' if column_exists(cr, P, 'shift_name') else 'NULL::varchar'
    own_planned = 'COALESCE(p.shift_is_planned, TRUE)' \
        if column_exists(cr, P, 'shift_is_planned') else 'TRUE'

    # ---------------- cantidades (Studio) ----------------
    buenas = 'COALESCE(p.x_studio_cantidad, 0)::float' \
        if column_exists(cr, P, 'x_studio_cantidad') else '0::float'
    averias = 'COALESCE(p.x_studio_averias, 0)::float' \
        if column_exists(cr, P, 'x_studio_averias') else '0::float'
    if buenas == '0::float':
        warnings.append('x_studio_cantidad no existe en productividad.')

    autorizada = 'COALESCE(l.oee_authorized_stop, FALSE)' \
        if column_exists(cr, 'mrp_workcenter_productivity_loss',
                         'oee_authorized_stop') else 'FALSE'

    # ---------------- operario ----------------
    joins_extra = ''
    if (column_exists(cr, P, 'employee_id')
            and column_exists(cr, 'hr_employee', 'name')):
        joins_extra += ' LEFT JOIN hr_employee emp ON emp.id = p.employee_id'
        operario = "COALESCE(emp.name, rp.name)"
    else:
        operario = 'rp.name'

    # ---------------- molde ----------------
    mold_join = ''
    std_mold = 'NULL::float'
    has_mold = (table_exists(cr, 'maintenance_equipment')
                and column_exists(cr, 'maintenance_equipment', 'cavity_count'))
    wo_mold = column_exists(cr, 'mrp_workorder', 'mold_id')
    op_mold = column_exists(cr, 'mrp_routing_workcenter', 'mold_id')
    if has_mold and (wo_mold or op_mold):
        parts = (['wo.mold_id'] if wo_mold else []) + (['op.mold_id'] if op_mold else [])
        mold_join = (' LEFT JOIN maintenance_equipment eq ON eq.id = COALESCE(%s)'
                     % ', '.join(parts))
        # Ciclo ACTUAL; si está vacío, el teórico (decisión de planta 21/10).
        cyc = ['NULLIF(eq.%s, 0)' % c for c in ('cycle_time_current', 'cycle_time_theoretical')
               if column_exists(cr, 'maintenance_equipment', c)]
        if cyc:
            std_mold = ('CASE WHEN eq.id IS NOT NULL AND eq.cavity_count > 0 '
                        'THEN (COALESCE(%s) / eq.cavity_count) / 60.0 END'
                        % ', '.join(cyc))
    else:
        warnings.append('Sin módulo de moldes: el estándar sale solo del '
                        'ciclo manual de la operación.')
    std = ('COALESCE(%s, CASE WHEN op.time_cycle_manual > 0 '
           'THEN op.time_cycle_manual END)' % std_mold)
    std_source = ("CASE WHEN %s IS NOT NULL THEN 'mold' "
                  "WHEN op.time_cycle_manual > 0 THEN 'operation' "
                  "ELSE 'none' END" % std_mold)

    tclass = ("CASE WHEN {aut} THEN 'authorized' "
              "WHEN lt.loss_type IN ('productive', 'performance', 'quality') "
              "THEN 'running' ELSE 'unplanned' END").format(aut=autorizada)

    # ---------------- CT donde dos OT pueden correr a la vez ----------------
    rel = 'mrp_workcenter_mrp_workcenter_tag_rel'
    if table_exists(cr, rel):
        parallel = """EXISTS (
            SELECT 1 FROM {rel} tr JOIN mrp_workcenter_tag tg ON tg.id = tr.mrp_workcenter_tag_id
             WHERE tr.mrp_workcenter_id = wc.id
               AND tg.name = ANY (string_to_array(COALESCE(
                   (SELECT value FROM ir_config_parameter WHERE key = '{param}'),
                   '{default}'), ',')))""".format(
            rel=rel, param=PARALLEL_PARAM, default=PARALLEL_DEFAULT)
    else:
        parallel = 'FALSE'

    win = windows_sql(
        cr, "(%(df)s::date - 3)", "(%(dt)s::date + 3)",
        'rc.id IN (SELECT DISTINCT resource_calendar_id FROM mrp_workcenter)')

    sql = """
        WITH base AS (
            SELECT
                p.id                                    AS pid,
                p.workcenter_id                         AS workcenter_id,
                p.company_id                            AS company_id,
                {own_date}                              AS own_date,
                {own_name}                              AS own_name,
                {own_planned}                           AS own_planned,
                p.date_start                            AS s,
                COALESCE(p.date_end, NOW() AT TIME ZONE 'UTC') AS e,
                COALESCE(p.duration, 0)::float          AS min_bruto,
                p.workorder_id                          AS workorder_id,
                wo.production_id                        AS production_id,
                mp.product_id                           AS product_id,
                {operario}                              AS operario,
                p.loss_id                               AS loss_id,
                lt.loss_type                            AS loss_type,
                {autorizada}                            AS authorized_stop,
                {tclass}                                AS time_class,
                CASE {tclass} WHEN 'unplanned' THEN 1
                              WHEN 'authorized' THEN 2 ELSE 3 END AS prio,
                {std_source}                            AS std_source,
                {std}                                   AS std_min_unit,
                {buenas}                                AS buenas,
                {averias}                               AS averias,
                COALESCE(wc.costs_hour, 0)              AS costs_hour,
                COALESCE(wc.oee_target, 0)              AS oee_target,
                wc.resource_calendar_id                 AS calendar_id,
                {parallel}                              AS paralelo
            FROM {P} p
            JOIN mrp_workcenter wc                       ON wc.id = p.workcenter_id
            LEFT JOIN mrp_workcenter_productivity_loss l  ON l.id = p.loss_id
            LEFT JOIN mrp_workcenter_productivity_loss_type lt ON lt.id = l.loss_id
            LEFT JOIN mrp_workorder wo                    ON wo.id = p.workorder_id
            LEFT JOIN mrp_production mp                   ON mp.id = wo.production_id
            LEFT JOIN mrp_routing_workcenter op           ON op.id = wo.operation_id
            LEFT JOIN res_users ru                        ON ru.id = p.user_id
            LEFT JOIN res_partner rp                      ON rp.id = ru.partner_id
            {mold_join}
            {joins_extra}
            -- Solo las líneas que pueden tocar turnos del rango (una línea
            -- válida dura máximo 12 h; se deja margen de 2 días).
            WHERE p.date_start >= (%(df)s::date - 2)
              AND p.date_start <  (%(dt)s::date + 3)
        ),
        b2 AS (
            SELECT base.*,
                   GREATEST(EXTRACT(EPOCH FROM (e - s)) / 60.0, 0) AS min_linea,
                   (e - s) > INTERVAL '{forgotten} hours' AS olvidada
              FROM base
        ),
        win AS MATERIALIZED ({win}),
        -- 1) Reparto entre los turnos que la línea atraviesa
        -- 1) Reparto entre los turnos que la línea atraviesa. Se cruza por
        --    (calendario, fecha operativa) con igualdad para que sea rápido: una
        --    línea de hasta 12 h solo puede tocar turnos del día anterior, del
        --    mismo día o del siguiente.
        cand_dias AS MATERIALIZED (
            SELECT b.pid, b.calendar_id, b.s, b.e,
                   ((b.s AT TIME ZONE 'UTC') AT TIME ZONE '{tz}')::date + d.k AS dia
              FROM b2 b CROSS JOIN (VALUES (-1), (0), (1)) AS d(k)
             WHERE NOT b.olvidada AND b.calendar_id IS NOT NULL
        ),
        cortes AS (
            SELECT c.pid, w.shift_name, w.shift_date, w.planned,
                   GREATEST(c.s, w.ws) AS s, LEAST(c.e, w.we) AS e
              FROM cand_dias c
              JOIN win w ON w.calendar_id = c.calendar_id AND w.shift_date = c.dia
             WHERE w.ws < c.e AND w.we > c.s
        ),
        tramos AS (
            SELECT pid, shift_name, shift_date, planned, s, e FROM cortes
            UNION ALL
            -- línea sin calendario o fuera de toda ventana: un tramo con su turno propio
            SELECT b.pid, b.own_name, b.own_date, b.own_planned, b.s, b.e
              FROM b2 b
             WHERE NOT b.olvidada
               AND NOT EXISTS (SELECT 1 FROM cortes c WHERE c.pid = b.pid)
            UNION ALL
            -- línea olvidada: un tramo de cero minutos, solo para revisión
            SELECT b.pid, b.own_name, b.own_date, b.own_planned, b.s, b.s
              FROM b2 b WHERE b.olvidada
        ),
        t2 AS MATERIALIZED (
            SELECT t.*, b.workcenter_id, b.prio, b.paralelo,
                   COALESCE(t.shift_date, DATE '1900-01-01') AS k_date,
                   COALESCE(t.shift_name, '') AS k_name,
                   ROW_NUMBER() OVER (PARTITION BY t.pid ORDER BY t.s, t.shift_date) AS rn,
                   EXTRACT(EPOCH FROM (t.e - t.s)) / 60.0 AS min_tramo
              FROM tramos t JOIN b2 b ON b.pid = t.pid
        ),
        -- 2) Reloj de la máquina contado una vez (salvo CT paralelos)
        --    Los tramos ya están dentro de un turno: los traslapes se buscan
        --    dentro de (máquina, fecha operativa, turno), que es rápido.
        pts AS (
            SELECT workcenter_id, k_date, k_name, s AS t
              FROM t2 WHERE NOT paralelo AND e > s
            UNION
            SELECT workcenter_id, k_date, k_name, e
              FROM t2 WHERE NOT paralelo AND e > s
        ),
        seg AS (
            SELECT workcenter_id, k_date, k_name, t AS t0,
                   LEAD(t) OVER (PARTITION BY workcenter_id, k_date, k_name
                                 ORDER BY t) AS t1
              FROM pts
        ),
        cubre AS (
            SELECT sg.workcenter_id, sg.t0, t.pid, t.rn, t.prio, t.s,
                   EXTRACT(EPOCH FROM (sg.t1 - sg.t0)) / 60.0 AS m,
                   MIN(t.prio) OVER (PARTITION BY sg.workcenter_id, sg.t0) AS mejor
              FROM seg sg
              JOIN t2 t ON t.workcenter_id = sg.workcenter_id AND NOT t.paralelo
                       AND t.k_date = sg.k_date AND t.k_name = sg.k_name
                       AND t.s <= sg.t0 AND t.e >= sg.t1
             WHERE sg.t1 > sg.t0
        ),
        cand AS (
            SELECT c.*,
                   COUNT(*) OVER (PARTITION BY workcenter_id, t0) AS n,
                   ROW_NUMBER() OVER (PARTITION BY workcenter_id, t0
                                      ORDER BY s DESC, pid DESC) AS orden
              FROM cubre c WHERE c.prio = c.mejor
        ),
        -- Parada registrada: el tramo es de la parada más reciente.
        -- Solo líneas operando: el tiempo se reparte en partes iguales.
        gana AS (
            SELECT pid, rn, CASE WHEN mejor = 3 THEN m / n ELSE m END AS m
              FROM cand
             WHERE mejor = 3 OR orden = 1
        ),
        efectivo AS (SELECT pid, rn, SUM(m) AS m FROM gana GROUP BY pid, rn),
        x AS (
            SELECT b.*, t.rn, t.shift_name, t.shift_date, t.planned, t.min_tramo,
                   CASE WHEN b.paralelo THEN t.min_tramo
                        ELSE COALESCE(ef.m, 0) END::float AS dur,
                   CASE WHEN b.olvidada THEN 0
                        WHEN b.min_linea > 0 THEN t.min_tramo / b.min_linea
                        ELSE 1 END                        AS frac
              FROM t2 t
              JOIN b2 b ON b.pid = t.pid
              LEFT JOIN efectivo ef ON ef.pid = t.pid AND ef.rn = t.rn
        )
        SELECT
            x.pid * 64 + x.rn                       AS id,
            x.pid                                   AS productivity_id,
            (x.rn = 1)                              AS es_primera,
            x.workcenter_id, x.company_id, x.shift_date, x.shift_name,
            COALESCE(substring(x.shift_name from '(Turno ?[0-9]+)'),
                     x.shift_name)                  AS shift_label,
            x.planned                               AS shift_is_planned,
            x.s                                     AS date_start,
            x.workorder_id, x.production_id, x.product_id, x.operario,
            x.loss_id, x.loss_type, x.authorized_stop, x.time_class,
            x.std_source, x.std_min_unit, x.paralelo, x.olvidada,
            CASE WHEN x.rn = 1 THEN x.min_bruto ELSE 0 END AS min_bruto,
            GREATEST(x.min_tramo - x.dur, 0)        AS min_traslape,
            x.dur                                   AS min_registrado,
            CASE WHEN x.time_class = 'running'    THEN x.dur ELSE 0 END AS min_operando,
            CASE WHEN x.time_class = 'running' AND x.std_min_unit IS NOT NULL
                 THEN x.dur ELSE 0 END              AS min_operando_std,
            CASE WHEN x.time_class = 'authorized' THEN x.dur ELSE 0 END AS min_autorizada,
            CASE WHEN x.time_class = 'unplanned'  THEN x.dur ELSE 0 END AS min_no_programada,
            x.buenas * x.frac                       AS unidades_buenas,
            x.averias * x.frac                      AS unidades_averias,
            CASE WHEN x.rn = 1 THEN x.buenas ELSE 0 END AS unidades_linea,
            COALESCE((x.buenas + x.averias) * x.frac * x.std_min_unit, 0) AS min_estandar,
            COALESCE(x.buenas * x.frac * x.std_min_unit, 0) AS min_valioso,
            CASE WHEN x.time_class = 'unplanned' AND x.rn = 1 AND NOT x.olvidada
                 THEN 1 ELSE 0 END                  AS eventos_parada,
            CASE WHEN x.time_class = 'unplanned' AND x.rn = 1 AND NOT x.olvidada
                      AND x.min_linea > 0 AND x.min_linea < {micro}
                 THEN 1 ELSE 0 END                  AS microparadas,
            x.costs_hour, x.oee_target
        FROM x
        WHERE x.shift_date BETWEEN %(df)s AND %(dt)s
    """.format(
        P=P, own_date=own_date, own_name=own_name, own_planned=own_planned,
        operario=operario, autorizada=autorizada, tclass=tclass,
        std_source=std_source, std=std, buenas=buenas, averias=averias,
        micro=MICROSTOP_MINUTES, mold_join=mold_join, joins_extra=joins_extra,
        parallel=parallel, forgotten=FORGOTTEN_HOURS, win=win,
        tz=FALLBACK_TZ)
    for w in warnings:
        _logger.debug('mrp_oee_report: %s', w)
    return sql
