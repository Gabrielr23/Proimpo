# -*- coding: utf-8 -*-
"""SQL común del OEE (una fila por línea de seguimiento de tiempo).

Modelo de minutos (igual al tablero de Access):

    registrado  = operando + autorizada + no_programada
    cargado     = registrado - autorizada          (base de Disponibilidad)
    D = operando / cargado
    R = estandar / operando_std                     (solo líneas con ciclo estándar)
    C = buenas / (buenas + averias)
    OEE = D x R x C

Clasificación del tiempo de cada línea según su motivo de pérdida:
  * autorizada  -> motivo con la casilla "Parada autorizada" (setup, purga...)
  * operando    -> categoría Productivo, Rendimiento o Calidad: la máquina
                   corría (lenta o haciendo defectos); esa pérdida sale de las
                   unidades contra el estándar, no del reloj
  * no_programada -> Disponibilidad o sin categoría

Compatible Odoo 18 y 19: la categoría se lee de la tabla de tipos de pérdida
(en 19 `loss_type` ya no está almacenado ni en el motivo ni en la línea).
Todas las columnas opcionales (turnos, moldes, operario) se detectan antes.
"""
import logging

_logger = logging.getLogger(__name__)

MICROSTOP_MINUTES = 5.0
FALLBACK_TZ = 'America/Bogota'


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


def build_line_sql(cr):
    P = 'mrp_workcenter_productivity'
    warnings = []

    # ---------------- turnos (mrp_shift_resolver) ----------------
    if column_exists(cr, P, 'shift_date'):
        shift_date = 'p.shift_date'
    else:
        shift_date = ("(p.date_start AT TIME ZONE 'UTC' AT TIME ZONE '%s')::date"
                      % FALLBACK_TZ)
        warnings.append('shift_date no existe: se usa la fecha de inicio.')
    shift_name = 'p.shift_name' if column_exists(cr, P, 'shift_name') else 'NULL::varchar'
    planned = 'COALESCE(p.shift_is_planned, TRUE)' \
        if column_exists(cr, P, 'shift_is_planned') else 'TRUE'

    # ---------------- cantidades (Studio) ----------------
    buenas = 'COALESCE(p.x_studio_cantidad, 0)::float' \
        if column_exists(cr, P, 'x_studio_cantidad') else '0::float'
    averias = 'COALESCE(p.x_studio_averias, 0)::float' \
        if column_exists(cr, P, 'x_studio_averias') else '0::float'
    if buenas == '0::float':
        warnings.append('x_studio_cantidad no existe en productividad.')

    # ---------------- motivo autorizado ----------------
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

    # ---------------- molde (mrp_mold_management) ----------------
    mold_join = ''
    std_mold = 'NULL::float'
    has_mold = (table_exists(cr, 'maintenance_equipment')
                and column_exists(cr, 'maintenance_equipment', 'cavity_count'))
    wo_mold = column_exists(cr, 'mrp_workorder', 'mold_id')
    op_mold = column_exists(cr, 'mrp_routing_workcenter', 'mold_id')
    if has_mold and (wo_mold or op_mold):
        parts = []
        if wo_mold:
            parts.append('wo.mold_id')
        if op_mold:
            parts.append('op.mold_id')
        mold_join = (' LEFT JOIN maintenance_equipment eq ON eq.id = COALESCE(%s)'
                     % ', '.join(parts))
        # Ciclo ESTÁNDAR = teórico; el actual solo si el teórico está vacío.
        cyc = []
        for c in ('cycle_time_theoretical', 'cycle_time_current'):
            if column_exists(cr, 'maintenance_equipment', c):
                cyc.append('NULLIF(eq.%s, 0)' % c)
        if cyc:
            std_mold = ('CASE WHEN eq.id IS NOT NULL AND eq.cavity_count > 0 '
                        'THEN (COALESCE(%s) / eq.cavity_count) / 60.0 END'
                        % ', '.join(cyc))
    else:
        warnings.append('Sin módulo de moldes: el estándar sale solo del '
                        'ciclo manual de la operación.')

    # minutos estándar por unidad: molde -> ciclo manual de la operación
    std = ('COALESCE(%s, CASE WHEN op.time_cycle_manual > 0 '
           'THEN op.time_cycle_manual END)' % std_mold)
    std_source = ("CASE WHEN %s IS NOT NULL THEN 'mold' "
                  "WHEN op.time_cycle_manual > 0 THEN 'operation' "
                  "ELSE 'none' END" % std_mold)

    tclass = ("CASE WHEN {aut} THEN 'authorized' "
              "WHEN lt.loss_type IN ('productive', 'performance', 'quality') "
              "THEN 'running' ELSE 'unplanned' END").format(aut=autorizada)

    dur = 'COALESCE(p.duration, 0)::float'
    sql = """
        SELECT
            p.id                                    AS id,
            p.workcenter_id                         AS workcenter_id,
            p.company_id                            AS company_id,
            {shift_date}                            AS shift_date,
            {shift_name}                            AS shift_name,
            COALESCE(substring({shift_name} from '(Turno ?[0-9]+)'),
                     {shift_name})                  AS shift_label,
            {planned}                               AS shift_is_planned,
            p.date_start                            AS date_start,
            p.workorder_id                          AS workorder_id,
            wo.production_id                        AS production_id,
            mp.product_id                           AS product_id,
            {operario}                              AS operario,
            p.loss_id                               AS loss_id,
            lt.loss_type                            AS loss_type,
            {autorizada}                            AS authorized_stop,
            {tclass}                                AS time_class,
            {std_source}                            AS std_source,
            {std}                                   AS std_min_unit,

            {dur}                                   AS min_registrado,
            CASE WHEN {tclass} = 'running'    THEN {dur} ELSE 0 END AS min_operando,
            CASE WHEN {tclass} = 'running' AND {std} IS NOT NULL
                 THEN {dur} ELSE 0 END              AS min_operando_std,
            CASE WHEN {tclass} = 'authorized' THEN {dur} ELSE 0 END AS min_autorizada,
            CASE WHEN {tclass} = 'unplanned'  THEN {dur} ELSE 0 END AS min_no_programada,
            {buenas}                                AS unidades_buenas,
            {averias}                               AS unidades_averias,
            COALESCE(({buenas} + {averias}) * {std}, 0) AS min_estandar,
            COALESCE({buenas} * {std}, 0)           AS min_valioso,
            CASE WHEN {tclass} = 'unplanned' THEN 1 ELSE 0 END AS eventos_parada,
            CASE WHEN {tclass} = 'unplanned' AND {dur} > 0
                      AND {dur} < {micro} THEN 1 ELSE 0 END AS microparadas,
            COALESCE(wc.costs_hour, 0)              AS costs_hour,
            COALESCE(wc.oee_target, 0)              AS oee_target
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
    """.format(
        P=P, shift_date=shift_date, shift_name=shift_name, planned=planned,
        operario=operario, autorizada=autorizada, tclass=tclass,
        std_source=std_source, std=std, dur=dur, buenas=buenas,
        averias=averias, micro=MICROSTOP_MINUTES, mold_join=mold_join,
        joins_extra=joins_extra)
    for w in warnings:
        _logger.warning('mrp_oee_report: %s', w)
    return sql
