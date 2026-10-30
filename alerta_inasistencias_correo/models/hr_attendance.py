# -*- coding: utf-8 -*-
"""Motor de generación y envío del reporte de inasistencias a RH.

Este archivo es código normal de un módulo de Odoo (NO pasa por el sandbox
restringido de las Acciones de Servidor), así que puede usar todo lo que un
programa Python normal usa: imports de librerías externas (xlsxwriter),
f-strings, comprensiones, funciones anidadas, etc.

La lógica de clasificación (quién es una inasistencia, con qué hora
esperada) es la misma de "inasistencias_hoy (V4).py" — ver
SDD_Reporte_Inasistencias.md para las reglas de negocio de origen, y
PLAN_Modulo_Alerta_Correo_RH.md para las decisiones de este módulo
(horarios de envío, columnas del correo, copia de respaldo, etc.).

Se agrega como método de hr.attendance (no de res.company: el reporte es
sobre asistencia, así que ese es su hogar natural) para que tanto los
ir.cron programados como el botón del asistente (ver wizard/) lo invoquen
con una sola línea:

    self.env['hr.attendance']._ejecutar_alerta_inasistencias()

Los métodos son privados (prefijo _): no se pueden invocar por RPC desde
fuera de Odoo, solo desde código del servidor (ir.cron y el asistente).
"""

import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import models, api

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
# Compañía(s) a evaluar. Deja vacío [] para evaluar todas las compañías activas.
COMPANY_IDS = []

# Si True, incluye también empleados que SÍ tienen registro de asistencia
# pero no coincide con su horario planificado (llegadas fuera de turno, etc.)
# como advertencia adicional (no se cuentan como inasistencia dura).
INCLUIR_ADVERTENCIAS_HORARIO = True

# Minutos de tolerancia después de la hora de entrada esperada antes de
# considerar al empleado como "inasistencia" (regla 5.4 del SDD). Solo
# aplica cuando se evalúa el día de hoy; para una fecha ya cerrada (el
# resumen evaluando "ayer") no hace falta, ver generar_reporte_inasistencias.
TOLERANCIA_MINUTOS = 15

# Zona horaria de referencia. Debe coincidir con turnos.md y con la
# operación real (América/Bogotá).
TZ = pytz.timezone('America/Bogota')

# Genera y adjunta el Excel completo (igual que V4) en cada corrida.
EXPORTAR_EXCEL = True

# Envío por correo activo (a diferencia de V4, aquí es el propósito del
# proceso automático).
ENVIAR_POR_CORREO = True

# Nombres de los Parámetros del Sistema (Ajustes > Técnico > Parámetros del
# sistema) de donde se leen los destinatarios y el remitente. Ninguno de
# los tres correos queda escrito en este archivo.
PARAM_CORREO_RRHH = 'alerta_inasistencia.correo_rrhh'
PARAM_CORREO_COPIA = 'alerta_inasistencia.correo_copia'
# Remitente que se muestra en el correo (para que no parezca enviado por el
# usuario que dispara el cron/botón, sino por una cuenta de notificaciones).
# Formato esperado: 'Nombre a mostrar <correo@dominio.com>', por ejemplo
# 'noreply <notificacionesodoo@proimpo.com>'. Si no se configura este
# parámetro, Odoo usa su comportamiento por defecto (el correo del usuario
# que ejecuta la acción). IMPORTANTE: para que no caiga en spam, esa
# dirección debería ser una cuenta real autorizada (SPF/DKIM) por el mismo
# servidor de correo saliente que ya tienen configurado en Odoo.
PARAM_CORREO_REMITENTE = 'alerta_inasistencia.correo_remitente'

# Cédulas a EXCLUIR por completo del reporte (no aparecen en ninguna
# categoría: Inasistencias, Aún no inicia turno, Con permiso, etc., ni se
# cuentan en el total de empleados evaluados). Pensado para casos como
# directivos o personal sin seguimiento de horario que de otra forma
# generarían ruido/falsos positivos en el reporte a RH.
#
# Se guarda como Parámetro del Sistema (no en este archivo) por lo mismo
# que los 3 correos de arriba: es un dato operativo (quién está exento)
# que cambia con el tiempo y que RH/administración debe poder ajustar
# desde Ajustes, sin pedir un despliegue de código. Un ir.config_parameter
# se guarda como texto sin límite práctico de tamaño, así que no hay
# problema en que la lista tenga 50 cédulas o más.
#
# Formato del valor: cédulas separadas por coma, p. ej. "123456,789012,...".
# Se pueden escribir con o sin puntos/espacios (se normalizan a solo
# dígitos antes de comparar contra la cédula del empleado).
PARAM_CEDULAS_EXCLUIDAS = 'alerta_inasistencia.cedulas_excluidas'

# Valores de la columna "Estado del turno" (✅ 2026-10-29). Indica de dónde
# salió la hora esperada del empleado:
#   Publicado -> turno de Planificación publicado (el empleado fue notificado).
#   Borrador  -> turno de Planificación SIN publicar: el empleado pudo no
#                haberse enterado; RH debe validarlo antes de tomar medidas.
#   Horario   -> no tiene turno en Planificación; se usó su horario de trabajo.
ESTADO_PUBLICADO = 'Publicado'
ESTADO_BORRADOR = 'Borrador'
ESTADO_HORARIO = 'Horario'


# ---------------------------------------------------------------------------
# UTILIDADES DE FECHA/HORA
# ---------------------------------------------------------------------------
def float_a_hora(valor_float):
    """Convierte un float tipo 8.5 (Odoo Time widget) a texto 'HH:MM'."""
    horas = int(valor_float)
    minutos = int(round((valor_float - horas) * 60))
    return f"{horas:02d}:{minutos:02d}"


def _rango_dia_utc(fecha_objetivo):
    """Dado un date en horario local (TZ), devuelve (inicio_utc, fin_utc)
    -naive, como Odoo guarda los datetime- que cubren ese día completo."""
    inicio_naive = datetime.combine(fecha_objetivo, time.min)
    fin_naive = datetime.combine(fecha_objetivo, time.max)
    inicio_utc = TZ.localize(inicio_naive).astimezone(pytz.utc).replace(tzinfo=None)
    fin_utc = TZ.localize(fin_naive).astimezone(pytz.utc).replace(tzinfo=None)
    return inicio_utc, fin_utc


def _normalizar_cedula(valor):
    """Deja solo dígitos, para poder comparar cédulas sin importar puntos,
    espacios o guiones con los que se hayan escrito en el Parámetro del
    Sistema o en la ficha del empleado (p. ej. '1.020.123.456' == '1020123456')."""
    if not valor:
        return ''
    return ''.join(ch for ch in str(valor) if ch.isdigit())


def _parsear_lista_cedulas(texto):
    if not texto:
        return set()
    return {
        _normalizar_cedula(c) for c in texto.split(',') if _normalizar_cedula(c)
    }


def cedulas_excluidas(env):
    """Lee el Parámetro del Sistema PARAM_CEDULAS_EXCLUIDAS y devuelve el
    conjunto de cédulas (normalizadas a solo dígitos) a excluir del reporte."""
    ConfigParam = env['ir.config_parameter'].sudo()
    return _parsear_lista_cedulas(ConfigParam.get_param(PARAM_CEDULAS_EXCLUIDAS))


# ---------------------------------------------------------------------------
# MOTOR DE CLASIFICACIÓN (misma lógica de V4, generalizada por fecha)
# ---------------------------------------------------------------------------
def generar_reporte_inasistencias(env, fecha_objetivo=None):
    """Cruza hr.attendance, resource.calendar / planning.slot, hr.leave y
    festivos/cierres para clasificar a los empleados activos según el árbol
    de decisión del SDD (sección 5.5), para la fecha objetivo indicada.

    fecha_objetivo: `date` en horario local. None = hoy (según TZ).
    Devuelve un dict con las listas clasificadas y metadatos del reporte.
    No escribe nada en Odoo (solo lectura).
    """
    now_tz = datetime.now(TZ)
    hoy_local = now_tz.date()
    if fecha_objetivo is None:
        fecha_objetivo = hoy_local
    es_fecha_actual = (fecha_objetivo == hoy_local)

    today_start_utc, today_end_utc = _rango_dia_utc(fecha_objetivo)
    ahora_float = now_tz.hour + now_tz.minute / 60.0

    # -- Empleados activos a evaluar -----------------------------------
    domain_emp = [('active', '=', True)]
    if COMPANY_IDS:
        domain_emp.append(('company_id', 'in', COMPANY_IDS))
    empleados = env['hr.employee'].sudo().search(domain_emp)

    # -- Exclusión por cédula (Parámetro del Sistema) -------------------
    excluidas = cedulas_excluidas(env)
    if excluidas:
        total_antes = len(empleados)
        empleados = empleados.filtered(
            lambda e: _normalizar_cedula(e.identification_id) not in excluidas
        )
        _logger.info(
            "Exclusión por cédula activa (%s cédula(s) en el parámetro): "
            "%s empleado(s) excluido(s) del reporte.",
            len(excluidas), total_antes - len(empleados),
        )

    # -- Precálculo de festivos y cierres generales para fecha_objetivo -
    PublicHolidayLine = env.get('hr.holidays.public.line')
    lineas_festivo = (
        PublicHolidayLine.sudo().search([('date', '=', fecha_objetivo)])
        if PublicHolidayLine is not None else PublicHolidayLine
    )

    CalendarLeaves = env.get('resource.calendar.leaves')
    _cierres_por_calendario = {}  # calendar_id -> nombre del cierre o False

    def _cierre_general_calendario(calendar):
        if CalendarLeaves is None or not calendar:
            return False
        if calendar.id not in _cierres_por_calendario:
            cierre = CalendarLeaves.sudo().search([
                ('resource_id', '=', False),
                ('calendar_id', 'in', [calendar.id, False]),
                ('date_from', '<=', today_end_utc),
                ('date_to', '>=', today_start_utc),
            ], limit=1)
            _cierres_por_calendario[calendar.id] = (
                (cierre.name or 'Cierre general') if cierre else False
            )
        return _cierres_por_calendario[calendar.id]

    def pais_referencia(employee):
        # Odoo 17+ eliminó hr.employee.address_home_id: la dirección privada
        # ahora vive en campos propios del empleado (private_country_id /
        # private_state_id). ✅ Corregido 2026-10-29.
        if employee.private_country_id:
            return employee.private_country_id
        if employee.address_id and employee.address_id.country_id:
            return employee.address_id.country_id
        if employee.company_id:
            return employee.company_id.country_id
        return False

    def estado_referencia(employee):
        if employee.private_state_id:
            return employee.private_state_id
        if employee.address_id and employee.address_id.state_id:
            return employee.address_id.state_id
        return False

    def es_dia_festivo(employee):
        if lineas_festivo:
            pais_emp = pais_referencia(employee)
            estado_emp = estado_referencia(employee)
            for l in lineas_festivo:
                year = l.year_id
                country_ok = (not year.country_id) or (pais_emp and pais_emp == year.country_id)
                state_ok = (not year.state_ids) or (estado_emp and estado_emp in year.state_ids)
                if country_ok and state_ok:
                    return l.name
        return _cierre_general_calendario(employee.resource_calendar_id)

    # -- Horarios de trabajo (resource.calendar) -------------------------
    def _lineas_validas(calendar):
        # Sin secciones (horarios de 2 semanas) ni la línea de almuerzo.
        return calendar.attendance_ids.filtered(
            lambda l: not l.display_type and l.day_period != 'lunch'
        )

    _cache_calendario_24h = {}

    def es_calendario_24h(calendar):
        """True si algún día del horario cubre las 24 h completas (p. ej.
        'Horario Operarios rotativo 42 h': 00-08, 08-16, 16-24 todos los
        días). Un horario así no dice cuándo trabaja realmente el empleado
        -eso lo dice Planificación-, así que no sirve para decidir si debía
        trabajar ni su hora de entrada. ✅ 2026-10-29."""
        if calendar.id not in _cache_calendario_24h:
            es_24h = False
            lineas = _lineas_validas(calendar)
            for dia in range(7):
                ls = lineas.filtered(lambda l, d=dia: int(l.dayofweek) == d)
                if (ls and min(ls.mapped('hour_from')) < 0.01
                        and max(ls.mapped('hour_to')) >= 23.99
                        and sum(l.hour_to - l.hour_from for l in ls) >= 23.99):
                    es_24h = True
                    break
            _cache_calendario_24h[calendar.id] = es_24h
        return _cache_calendario_24h[calendar.id]

    def lineas_turno_dia(calendar):
        """Líneas del horario que INICIAN un turno en fecha_objetivo. Se
        descarta la línea de 00:00 cuando continúa un turno que el día
        anterior terminó a las 24:00 (turno nocturno partido, p. ej. T3
        21:30 -> 06:00): ese tramo pertenece al día en que empezó el turno,
        no al día siguiente. ✅ 2026-10-29."""
        lineas = _lineas_validas(calendar)
        weekday = fecha_objetivo.weekday()  # 0 = lunes ... 6 = domingo
        dia_anterior = (weekday - 1) % 7
        del_dia = lineas.filtered(
            lambda l: int(l.dayofweek) == weekday
        ).sorted(key=lambda l: l.hour_from)
        ayer_termina_24 = any(
            l.hour_to >= 23.99 for l in lineas if int(l.dayofweek) == dia_anterior
        )
        if ayer_termina_24:
            del_dia = del_dia.filtered(lambda l: l.hour_from >= 0.01)
        return del_dia

    # -- Planificación (planning.slot) -----------------------------------
    PlanningSlot = env.get('planning.slot')

    def turno_planning_dia(employee):
        """Turno de Planificación que INICIA en fecha_objetivo (publicado o
        borrador). Un turno que empezó ayer y termina hoy (T3) pertenece a
        ayer. Si hay publicados y borradores el mismo día, prevalece el
        publicado. Devuelve (slot, estado) o None. ✅ 2026-10-29."""
        if PlanningSlot is None:
            return None
        slots = PlanningSlot.sudo().search([
            ('employee_id', '=', employee.id),
            ('start_datetime', '>=', today_start_utc),
            ('start_datetime', '<=', today_end_utc),
        ], order='start_datetime asc')
        publicados = slots.filtered(lambda s: s.state == 'published')
        if publicados:
            return publicados[0], ESTADO_PUBLICADO
        if slots:
            return slots[0], ESTADO_BORRADOR
        return None

    def hora_entrada_planning(slot):
        dt_local = pytz.utc.localize(slot.start_datetime).astimezone(TZ)
        hora_float = dt_local.hour + dt_local.minute / 60.0
        return dt_local.strftime('%H:%M'), hora_float

    def tiene_ausencia_aprobada(employee):
        HrLeave = env['hr.leave'].sudo()
        return HrLeave.search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', today_end_utc),
            ('date_to', '>=', today_start_utc),
        ])

    def tiene_asistencia(employee):
        HrAttendance = env['hr.attendance'].sudo()
        return HrAttendance.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', today_start_utc),
            ('check_in', '<=', today_end_utc),
        ])

    inasistencias = []          # Falta confirmada
    pendientes_por_llegar = []  # Solo aplica si es_fecha_actual (ver más abajo)
    con_permiso = []
    sin_horario_definido = []   # Sin horario y sin Planificación (solo consola/log)
    sin_planificacion = []      # Horario de 24 h y sin turno ese día (✅ 2026-10-29)
    advertencias_horario = []
    marcaron_en_festivo = []
    festivos_detectados = set()

    for emp in empleados:
        cedula = emp.identification_id or 'N/A'
        area = emp.department_id.name or 'Sin área'

        festivo = es_dia_festivo(emp)
        if festivo:
            festivos_detectados.add(festivo)
            if INCLUIR_ADVERTENCIAS_HORARIO and tiene_asistencia(emp):
                marcaron_en_festivo.append({
                    'cedula': cedula,
                    'nombre': emp.name,
                    'area': area,
                    'entrada_esperada': '-',
                    'estado_turno': '-',
                    'employee': emp,
                    'tipo_ausencia': festivo,
                })
            continue

        asistencias = tiene_asistencia(emp)
        ausencias = tiene_ausencia_aprobada(emp)
        calendar = emp.resource_calendar_id
        turno = turno_planning_dia(emp)

        fila = {
            'cedula': cedula,
            'nombre': emp.name,
            'area': area,
            'entrada_esperada': '-',
            'estado_turno': '-',
            'employee': emp,
        }

        if ausencias:
            if not asistencias:
                fila['tipo_ausencia'] = ausencias[0].holiday_status_id.name
                con_permiso.append(fila)
            continue

        # ¿Debía trabajar y a qué hora? Prioridad: 1) Planificación,
        # 2) horario de trabajo (si no es de 24 h). Ver punto 9 del plan.
        if turno:
            slot, estado = turno
            debe_trabajar = True
            entrada_txt, entrada_float = hora_entrada_planning(slot)
        elif calendar and not es_calendario_24h(calendar):
            lineas = lineas_turno_dia(calendar)
            debe_trabajar = bool(lineas)
            estado = ESTADO_HORARIO
            if lineas:
                entrada_float = lineas[0].hour_from
                entrada_txt = float_a_hora(entrada_float)
            else:
                entrada_txt, entrada_float = None, None
        elif calendar:
            # Horario de 24 h (rotativo) sin turno en Planificación ese día:
            # no se puede saber si descansaba o si faltó cargar/publicar el
            # turno -> categoría "Sin planificación" (opción b, 2026-10-29).
            if not asistencias:
                sin_planificacion.append(fila)
            elif INCLUIR_ADVERTENCIAS_HORARIO:
                advertencias_horario.append(fila)
            continue
        else:
            if not asistencias:
                sin_horario_definido.append(fila)
            continue

        fila['entrada_esperada'] = entrada_txt or '-'
        if debe_trabajar:
            fila['estado_turno'] = estado

        if debe_trabajar and not asistencias:
            if not es_fecha_actual:
                # Fecha ya cerrada: no existe "aún no inicia turno" para un
                # día que ya terminó por completo -> se confirma
                # directamente como inasistencia (esto es lo que permite
                # re-consultar en vez de depender de un histórico congelado,
                # ver punto 6 de PLAN_Modulo_Alerta_Correo_RH.md).
                inasistencias.append(fila)
            elif entrada_float is not None:
                # Regla de tolerancia 5.4 del SDD, solo para el día de hoy.
                limite = entrada_float + (TOLERANCIA_MINUTOS / 60.0)
                if ahora_float < limite:
                    pendientes_por_llegar.append(fila)
                else:
                    inasistencias.append(fila)
            else:
                inasistencias.append(fila)
        elif not debe_trabajar and asistencias and INCLUIR_ADVERTENCIAS_HORARIO:
            advertencias_horario.append(fila)

    for lista in (
        inasistencias, con_permiso, sin_horario_definido, sin_planificacion,
        advertencias_horario, pendientes_por_llegar, marcaron_en_festivo,
    ):
        lista.sort(key=lambda f: (f['area'], f['nombre']))

    return {
        'fecha_objetivo': fecha_objetivo,
        'es_fecha_actual': es_fecha_actual,
        'generado_en': now_tz,
        'fecha_hora_texto': now_tz.strftime('%Y-%m-%d %H:%M:%S'),
        'total_empleados_evaluados': len(empleados),
        'inasistencias': inasistencias,
        'pendientes_por_llegar': pendientes_por_llegar,
        'con_permiso': con_permiso,
        'sin_horario_definido': sin_horario_definido,
        'sin_planificacion': sin_planificacion,
        'inasistencias_borrador': sum(
            1 for f in inasistencias if f.get('estado_turno') == ESTADO_BORRADOR
        ),
        'advertencias_horario': advertencias_horario,
        'marcaron_en_festivo': marcaron_en_festivo,
        'festivos_detectados': festivos_detectados,
    }


# ---------------------------------------------------------------------------
# SALIDA EN CONSOLA/LOG (útil para pruebas manuales en la shell y para que
# quede rastro en los logs del servidor en cada corrida automática)
# ---------------------------------------------------------------------------
def imprimir_reporte_consola(reporte):
    """Imprime y deja en el log (_logger.info) el mismo resumen que V4
    mostraba en consola, a partir del dict de generar_reporte_inasistencias()."""

    def formato_tabla(filas, columnas_extra=None, clave_extra='tipo_ausencia'):
        lineas = []
        encabezado = f"  {'Cédula':<15} {'Nombre completo':<35} {'Área':<25} {'Entrada esp.':<12}"
        if columnas_extra:
            encabezado += f" {columnas_extra:<20}"
        lineas.append(encabezado)
        lineas.append("  " + "-" * (len(encabezado) - 2))
        for f in filas:
            linea = f"  {f['cedula']:<15} {f['nombre']:<35} {f['area']:<25} {f['entrada_esperada']:<12}"
            if columnas_extra:
                linea += f" {f.get(clave_extra, ''):<20}"
            lineas.append(linea)
        return '\n'.join(lineas)

    fecha_txt = reporte['fecha_objetivo'].isoformat()
    partes = [
        "=" * 80,
        "REPORTE DE INASISTENCIAS",
        f"Fecha evaluada: {fecha_txt}"
        f"{' (hoy)' if reporte['es_fecha_actual'] else ' (día cerrado, re-consultado)'}",
        f"Generado: {reporte['fecha_hora_texto']} ({TZ.zone})",
        f"Total empleados activos evaluados: {reporte['total_empleados_evaluados']}",
        "=" * 80,
    ]

    if reporte['festivos_detectados']:
        partes.append(f"📅 Festivo(s)/cierre(s) detectado(s): {', '.join(reporte['festivos_detectados'])}")

    partes.append("\n--- ❌ INASISTENCIAS ---")
    partes.append(formato_tabla(reporte['inasistencias'], columnas_extra='Estado del turno', clave_extra='estado_turno') if reporte['inasistencias'] else "  Ninguna. ✅")
    partes.append(f"\nTotal inasistencias: {len(reporte['inasistencias'])}")
    if texto_inasistencias_borrador(reporte):
        partes.append(texto_inasistencias_borrador(reporte))

    if reporte['es_fecha_actual']:
        partes.append("\n--- 🕒 AÚN NO INICIA SU TURNO ---")
        partes.append(formato_tabla(reporte['pendientes_por_llegar'], columnas_extra='Estado del turno', clave_extra='estado_turno') if reporte['pendientes_por_llegar'] else "  Ninguno.")

    partes.append("\n--- 🟡 CON PERMISO/AUSENCIA APROBADA ---")
    partes.append(
        formato_tabla(reporte['con_permiso'], columnas_extra='Tipo de ausencia')
        if reporte['con_permiso'] else "  Ninguno."
    )

    partes.append("\n--- ⚪ SIN HORARIO/PLANIFICACIÓN DEFINIDA ---")
    partes.append(formato_tabla(reporte['sin_horario_definido']) if reporte['sin_horario_definido'] else "  Ninguno.")

    partes.append("\n--- 🔵 SIN PLANIFICACIÓN (horario rotativo de 24 h y sin turno ese día) ---")
    partes.append(formato_tabla(reporte['sin_planificacion']) if reporte['sin_planificacion'] else "  Ninguno.")

    if INCLUIR_ADVERTENCIAS_HORARIO:
        partes.append("\n--- ⚠️  MARCARON ASISTENCIA SIN TURNO/HORARIO ASIGNADO ---")
        partes.append(formato_tabla(reporte['advertencias_horario']) if reporte['advertencias_horario'] else "  Ninguno.")

        partes.append("\n--- 🟠 MARCARON ASISTENCIA EN DÍA FESTIVO/CIERRE ---")
        partes.append(
            formato_tabla(reporte['marcaron_en_festivo'], columnas_extra='Festivo/cierre')
            if reporte['marcaron_en_festivo'] else "  Ninguno."
        )

    texto = '\n'.join(partes)
    print(texto)          # visible al correr manualmente en la shell
    _logger.info(texto)   # visible en los logs del servidor en cada cron


# ---------------------------------------------------------------------------
# EXPORTAR REPORTE A EXCEL (.xlsx) COMO ADJUNTO EN ODOO — Excel COMPLETO con
# todas las hojas (decisión confirmada del plan, punto 4).
# ---------------------------------------------------------------------------
def exportar_reporte_excel(env, reporte):
    import io
    import base64
    import xlsxwriter

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    fmt_header = workbook.add_format({
        'bold': True, 'bg_color': '#D9534F', 'font_color': 'white', 'border': 1
    })
    fmt_header_ok = workbook.add_format({
        'bold': True, 'bg_color': '#5CB85C', 'font_color': 'white', 'border': 1
    })
    fmt_header_warn = workbook.add_format({
        'bold': True, 'bg_color': '#F0AD4E', 'font_color': 'white', 'border': 1
    })
    fmt_header_info = workbook.add_format({
        'bold': True, 'bg_color': '#5BC0DE', 'font_color': 'white', 'border': 1
    })
    fmt_cell = workbook.add_format({'border': 1})
    fmt_borrador = workbook.add_format({
        'border': 1, 'bold': True, 'bg_color': '#FCE8B2', 'font_color': '#8A5A00'
    })

    def escribir_hoja(nombre_hoja, filas, columnas, color_header=fmt_header):
        """columnas: lista de (título, clave del dict de la fila, ancho)."""
        hoja = workbook.add_worksheet(nombre_hoja[:31])
        for col, (titulo, _clave, ancho) in enumerate(columnas):
            hoja.write(0, col, titulo, color_header)
            hoja.set_column(col, col, ancho)
        for fila_idx, f in enumerate(filas, start=1):
            for col, (_titulo, clave, _ancho) in enumerate(columnas):
                valor = f.get(clave, '')
                formato = (
                    fmt_borrador
                    if clave == 'estado_turno' and valor == ESTADO_BORRADOR
                    else fmt_cell
                )
                hoja.write(fila_idx, col, valor, formato)

    # Nota: se dejaron fuera del Excel a propósito las hojas "Sin horario
    # definido", "Advertencias horario" y "Asistio en festivo" (decisión
    # del 2026-09-02) — esas categorías se siguen calculando y viendo en la
    # consola/log. La hoja "Sin planificacion" y la columna "Estado del
    # turno" se agregaron el 2026-10-29 (puntos 9 y 10 del plan).
    col_cedula = ('Cédula', 'cedula', 15)
    col_nombre = ('Nombre completo', 'nombre', 32)
    col_area = ('Área', 'area', 25)
    col_entrada = ('Entrada esperada', 'entrada_esperada', 14)
    col_estado = ('Estado del turno', 'estado_turno', 16)
    columnas_base = [col_cedula, col_nombre, col_area, col_entrada]
    escribir_hoja('Inasistencias', reporte['inasistencias'],
                  columnas_base + [col_estado], fmt_header)
    escribir_hoja('Aun no inicia turno', reporte['pendientes_por_llegar'],
                  columnas_base + [col_estado], fmt_header_warn)
    escribir_hoja('Con permiso', reporte['con_permiso'],
                  columnas_base + [('Tipo de ausencia', 'tipo_ausencia', 22)], fmt_header_ok)
    escribir_hoja('Sin planificacion', reporte['sin_planificacion'],
                  [col_cedula, col_nombre, col_area], fmt_header_info)

    total_inas = len(reporte['inasistencias'])
    hoja_resumen = workbook.add_worksheet('Resumen')
    hoja_resumen.write(0, 0, 'Reporte de inasistencias', fmt_header)
    filas_resumen = [
        ('Fecha evaluada:', reporte['fecha_objetivo'].isoformat()),
        ('Fecha y hora de generación:', f"{reporte['fecha_hora_texto']} ({TZ.zone})"),
        ('Total inasistencias:', total_inas),
        ('Inasistencias con turno en borrador:', reporte['inasistencias_borrador']),
        ('Total aún no inicia turno:', len(reporte['pendientes_por_llegar'])),
        ('Total con permiso:', len(reporte['con_permiso'])),
        ('Total sin planificación:', len(reporte['sin_planificacion'])),
        ('Festivos/cierres detectados:',
         ', '.join(reporte['festivos_detectados']) if reporte['festivos_detectados'] else 'Ninguno'),
        ('Tolerancia aplicada (min):', TOLERANCIA_MINUTOS),
    ]
    for idx, (etiqueta, valor) in enumerate(filas_resumen, start=1):
        hoja_resumen.write(idx, 0, etiqueta)
        hoja_resumen.write(idx, 1, valor)
    texto_borrador = texto_inasistencias_borrador(reporte)
    if texto_borrador:
        hoja_resumen.write(len(filas_resumen) + 2, 0, texto_borrador, fmt_borrador)
    hoja_resumen.set_column(0, 0, 36)
    hoja_resumen.set_column(1, 1, 30)

    workbook.close()
    output.seek(0)
    datos_base64 = base64.b64encode(output.read())

    nombre_archivo = (
        f"Inasistencias_{reporte['fecha_objetivo'].isoformat()}_"
        f"{reporte['generado_en'].strftime('%H%M')}.xlsx"
    )
    attachment = env['ir.attachment'].sudo().create({
        'name': nombre_archivo,
        'type': 'binary',
        'datas': datos_base64,
        'mimetype': (
            'application/vnd.openxmlformats-officedocument'
            '.spreadsheetml.sheet'
        ),
        'public': False,
    })
    env.cr.commit()

    _logger.info("Reporte exportado como adjunto: '%s' (ir.attachment ID: %s)", nombre_archivo, attachment.id)
    return attachment


# ---------------------------------------------------------------------------
# TABLA HTML PARA EL CUERPO DEL CORREO (solo "Inasistencias", columnas del
# plan: Cédula, Nombre completo, Área/Departamento, Fecha, Hora esperada)
# ---------------------------------------------------------------------------
def texto_inasistencias_borrador(reporte):
    """Línea de encabezado (correo y Excel) que resume cuántas inasistencias
    vienen de turnos de Planificación en borrador. '' si no hay inasistencias."""
    total = len(reporte['inasistencias'])
    borr = reporte['inasistencias_borrador']
    if not total:
        return ''
    if total == 1:
        inicio = "De la 1 inasistencia,"
    else:
        inicio = f"De las {total} inasistencias,"
    verbo = "corresponde" if borr == 1 else "corresponden"
    return (
        f"{inicio} {borr} {verbo} a turnos en borrador "
        f"(no publicados en Planificación)."
    )


def construir_cuerpo_html(reporte):
    fecha_txt = reporte['fecha_objetivo'].strftime('%Y-%m-%d')
    total = len(reporte['inasistencias'])

    # Mismo criterio que el asunto del correo (ver enviar_correo_inasistencias):
    # se distingue "Consolidado" (resumen de un día ya cerrado, ej. ayer a
    # las 06:30) de las 3 alertas del día (hoy), para que no se confundan
    # al leerlos sin entrar al detalle.
    titulo = (
        f"Reporte de Inasistencias — {fecha_txt}" if reporte['es_fecha_actual']
        else f"Reporte de Inasistencias — Consolidado {fecha_txt}"
    )

    encabezado = f"""
    <h2 style="margin-bottom:4px;">{titulo}</h2>
    <p style="margin-top:0;">
      <strong>Total inasistencias: {total}</strong><br/>
      Generado: {reporte['fecha_hora_texto']} ({TZ.zone})
    </p>
    """

    texto_borrador = texto_inasistencias_borrador(reporte)
    if texto_borrador:
        encabezado += f'<p><strong>{texto_borrador}</strong>'
        if reporte['inasistencias_borrador']:
            encabezado += (
                '<br/><span style="color:#8A5A00;">Un turno en borrador no le '
                'fue notificado al empleado: valídalo con el planificador '
                'antes de tomar medidas.</span>'
            )
        encabezado += '</p>'

    if reporte['festivos_detectados']:
        encabezado += (
            f'<p>📅 Festivo(s)/cierre(s) detectado(s): '
            f'{", ".join(reporte["festivos_detectados"])}</p>'
        )

    if not reporte['inasistencias']:
        return encabezado + '<p>Sin inasistencias reportadas ✅</p>'

    celda = 'border:1px solid #ddd;padding:6px;'
    celda_borrador = celda + 'background-color:#FCE8B2;color:#8A5A00;font-weight:bold;'
    filas_html = ''.join(
        f"""<tr>
              <td style="{celda}">{f['cedula']}</td>
              <td style="{celda}">{f['nombre']}</td>
              <td style="{celda}">{f['area']}</td>
              <td style="{celda}">{fecha_txt}</td>
              <td style="{celda}">{f['entrada_esperada']}</td>
              <td style="{celda_borrador if f.get('estado_turno') == ESTADO_BORRADOR else celda}">{f.get('estado_turno', '-')}</td>
            </tr>"""
        for f in reporte['inasistencias']
    )

    th = 'border:1px solid #ddd;padding:6px;text-align:left;'
    tabla = f"""
    <table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;">
      <thead>
        <tr style="background-color:#D9534F;color:#ffffff;">
          <th style="{th}">Cédula</th>
          <th style="{th}">Nombre completo</th>
          <th style="{th}">Área/Departamento</th>
          <th style="{th}">Fecha</th>
          <th style="{th}">Hora esperada</th>
          <th style="{th}">Estado del turno</th>
        </tr>
      </thead>
      <tbody>
        {filas_html}
      </tbody>
    </table>
    """

    return encabezado + tabla


# ---------------------------------------------------------------------------
# ENVÍO DEL CORREO (RH + copia de respaldo en CC, leídos de Parámetros del
# Sistema — nada de correos fijos en el código, ver plan punto 5.4/6.1)
# ---------------------------------------------------------------------------
def _parsear_lista_correos(texto):
    if not texto:
        return []
    return [c.strip() for c in texto.split(',') if c.strip()]


def enviar_correo_inasistencias(env, reporte, adjunto=None):
    """Crea y envía el mail.mail a RH (con copia CC de respaldo). No
    interrumpe el resto del flujo si falla — el adjunto ya quedó guardado
    en Odoo independientemente de si el correo se pudo enviar."""
    ConfigParam = env['ir.config_parameter'].sudo()
    destinatarios = _parsear_lista_correos(ConfigParam.get_param(PARAM_CORREO_RRHH))
    copia = _parsear_lista_correos(ConfigParam.get_param(PARAM_CORREO_COPIA))
    remitente = (ConfigParam.get_param(PARAM_CORREO_REMITENTE) or '').strip()

    if not destinatarios:
        _logger.warning(
            "No se envió correo de inasistencias: falta configurar el "
            "Parámetro del Sistema '%s'.", PARAM_CORREO_RRHH,
        )
        return False

    fecha_txt = reporte['fecha_objetivo'].strftime('%Y-%m-%d')
    hora_txt = reporte['generado_en'].strftime('%H:%M')
    # ✅ Confirmado (2026-09-07): asuntos distintos para que RH no confunda
    # una alerta del día (hoy) con el consolidado de un día ya cerrado
    # (ayer, cron de las 06:30) sin tener que entrar al detalle del correo.
    if reporte['es_fecha_actual']:
        asunto = f"Reporte de Inasistencias — {fecha_txt} {hora_txt}"
    else:
        asunto = f"Reporte de Inasistencias — Consolidado {fecha_txt} {hora_txt}"

    valores_correo = {
        'subject': asunto,
        'body_html': construir_cuerpo_html(reporte),
        'email_to': ','.join(destinatarios),
    }
    if copia:
        valores_correo['email_cc'] = ','.join(copia)
    if remitente:
        # 'Nombre a mostrar <correo@dominio.com>', p. ej.
        # 'noreply <notificacionesodoo@proimpo.com>' — así el correo no
        # aparece enviado por el usuario que dispara el cron/botón.
        valores_correo['email_from'] = remitente
    if adjunto:
        valores_correo['attachment_ids'] = [(4, adjunto.id)]

    try:
        env['mail.mail'].sudo().create(valores_correo).send()
        env.cr.commit()
        _logger.info(
            "Correo de inasistencias enviado a: %s%s",
            ', '.join(destinatarios),
            f" (copia: {', '.join(copia)})" if copia else "",
        )
        return True
    except Exception:
        _logger.exception("Falló el envío del correo de inasistencias")
        return False


# ---------------------------------------------------------------------------
# PUNTO DE ENTRADA ÚNICO
# ---------------------------------------------------------------------------
def ejecutar_alerta_inasistencias(env, fecha_objetivo=None, imprimir_consola=True):
    """Genera el reporte, exporta el Excel (si EXPORTAR_EXCEL) y envía el
    correo (si ENVIAR_POR_CORREO), en ese orden.

    fecha_objetivo:
        None  -> hoy (usar para las 3 alertas del día: 07:00, 14:00, 23:15)
        date  -> esa fecha (usar para el resumen de las 06:30, pasando
                 "ayer": datetime.now(TZ).date() - timedelta(days=1))
    """
    reporte = generar_reporte_inasistencias(env, fecha_objetivo=fecha_objetivo)

    if imprimir_consola:
        imprimir_reporte_consola(reporte)

    adjunto = exportar_reporte_excel(env, reporte) if EXPORTAR_EXCEL else None

    correo_enviado = False
    if ENVIAR_POR_CORREO:
        correo_enviado = enviar_correo_inasistencias(env, reporte, adjunto)

    return {
        'reporte': reporte,
        'adjunto': adjunto,
        'correo_enviado': correo_enviado,
    }


# ---------------------------------------------------------------------------
# MÉTODOS EN hr.attendance — esto es lo que llaman el botón del asistente
# (wizard/alerta_inasistencias_wizard.py) y los ir.cron programados.
#
# ✅ 2026-10-29: los 3 métodos son PRIVADOS (prefijo _). Un método público
# de un modelo se puede invocar por RPC (JSON-RPC/XML-RPC) por cualquier
# usuario con acceso de lectura a hr.attendance, y como el reporte corre con
# sudo(), cualquier empleado habría podido disparar correos a RH. Los
# métodos con prefijo _ no son invocables por RPC; el código de un ir.cron
# sí puede llamarlos (es código del servidor), igual que el asistente.
#
# Se exponen 2 métodos sin parámetros para los cron (sin cálculo de fechas
# en el código del cron) y 1 genérico para el asistente o la shell.
# ---------------------------------------------------------------------------
class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    @api.model
    def _cron_alerta_inasistencias_hoy(self):
        """Para los ir.cron de las alertas del día (07:00, 14:00, 23:15).
        Código Python del cron:

            env['hr.attendance']._cron_alerta_inasistencias_hoy()
        """
        return self._ejecutar_alerta_inasistencias(fecha_objetivo=None)

    @api.model
    def _cron_alerta_inasistencias_resumen_ayer(self):
        """Para el ir.cron del resumen diario (06:30), que evalúa el día
        calendario anterior completo. Código Python del cron:

            env['hr.attendance']._cron_alerta_inasistencias_resumen_ayer()
        """
        ayer = datetime.now(TZ).date() - timedelta(days=1)
        return self._ejecutar_alerta_inasistencias(fecha_objetivo=ayer)

    @api.model
    def _ejecutar_alerta_inasistencias(self, fecha_objetivo=None, imprimir_consola=True):
        """Punto de entrada genérico (usado por el asistente y por los dos
        métodos de arriba). fecha_objetivo=None evalúa "hoy"."""
        return ejecutar_alerta_inasistencias(
            self.env, fecha_objetivo=fecha_objetivo, imprimir_consola=imprimir_consola,
        )
