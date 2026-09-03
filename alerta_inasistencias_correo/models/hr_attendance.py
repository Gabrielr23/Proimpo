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

    self.env['hr.attendance'].sudo().ejecutar_alerta_inasistencias()
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
        # Odoo 17+ eliminó hr.employee.address_home_id; la dirección de
        # residencia ahora se guarda en campos private_* directamente en el
        # empleado. Se usa _fields para no romper si el campo no existe.
        if 'private_country_id' in employee._fields and employee.private_country_id:
            return employee.private_country_id
        direccion = employee.address_id
        if direccion and direccion.country_id:
            return direccion.country_id
        if employee.company_id:
            return employee.company_id.country_id
        return False

    def estado_referencia(employee):
        if 'private_state_id' in employee._fields and employee.private_state_id:
            return employee.private_state_id
        direccion = employee.address_id
        if direccion and direccion.state_id:
            return direccion.state_id
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

    def debia_trabajar(employee):
        calendar = employee.resource_calendar_id
        if not calendar:
            return None
        weekday = fecha_objetivo.weekday()  # 0 = lunes ... 6 = domingo
        lineas_dia = calendar.attendance_ids.filtered(lambda l: int(l.dayofweek) == weekday)
        return bool(lineas_dia)

    def hora_entrada_calendario(employee):
        calendar = employee.resource_calendar_id
        if not calendar:
            return None, None
        weekday = fecha_objetivo.weekday()
        lineas_dia = calendar.attendance_ids.filtered(
            lambda l: int(l.dayofweek) == weekday
        ).sorted(key=lambda l: l.hour_from)
        if not lineas_dia:
            return None, None
        hora_float = lineas_dia[0].hour_from
        return float_a_hora(hora_float), hora_float

    def slots_planning(employee):
        PlanningSlot = env.get('planning.slot')
        if PlanningSlot is None:
            return None
        return PlanningSlot.sudo().search([
            ('employee_id', '=', employee.id),
            ('start_datetime', '<=', today_end_utc),
            ('end_datetime', '>=', today_start_utc),
        ], order='start_datetime asc')

    def hora_entrada_planning(slots):
        if not slots:
            return None, None
        primer_slot = slots[0]
        dt_utc = pytz.utc.localize(primer_slot.start_datetime)
        dt_local = dt_utc.astimezone(TZ)
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
    sin_horario_definido = []
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
                    'employee': emp,
                    'tipo_ausencia': festivo,
                })
            continue

        debia = debia_trabajar(emp)
        slots = slots_planning(emp)
        asistencias = tiene_asistencia(emp)
        ausencias = tiene_ausencia_aprobada(emp)

        if slots is not None and slots:
            debe_trabajar = True
            entrada_txt, entrada_float = hora_entrada_planning(slots)
        elif slots is not None and not slots and debia is False:
            debe_trabajar = False
            entrada_txt, entrada_float = None, None
        else:
            debe_trabajar = bool(debia)
            entrada_txt, entrada_float = (
                hora_entrada_calendario(emp) if debia else (None, None)
            )

        fila = {
            'cedula': cedula,
            'nombre': emp.name,
            'area': area,
            'entrada_esperada': entrada_txt or '-',
            'employee': emp,
        }

        if ausencias:
            if not asistencias:
                fila['tipo_ausencia'] = ausencias[0].holiday_status_id.name
                con_permiso.append(fila)
            continue

        if debia is None and (slots is None or not slots):
            if not asistencias:
                sin_horario_definido.append(fila)
            continue

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
        inasistencias, con_permiso, sin_horario_definido,
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

    def formato_tabla(filas, columnas_extra=None):
        lineas = []
        encabezado = f"  {'Cédula':<15} {'Nombre completo':<35} {'Área':<25} {'Entrada esp.':<12}"
        if columnas_extra:
            encabezado += f" {columnas_extra:<20}"
        lineas.append(encabezado)
        lineas.append("  " + "-" * (len(encabezado) - 2))
        for f in filas:
            linea = f"  {f['cedula']:<15} {f['nombre']:<35} {f['area']:<25} {f['entrada_esperada']:<12}"
            if columnas_extra:
                linea += f" {f.get('tipo_ausencia', ''):<20}"
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
    partes.append(formato_tabla(reporte['inasistencias']) if reporte['inasistencias'] else "  Ninguna. ✅")
    partes.append(f"\nTotal inasistencias: {len(reporte['inasistencias'])}")

    if reporte['es_fecha_actual']:
        partes.append("\n--- 🕒 AÚN NO INICIA SU TURNO ---")
        partes.append(formato_tabla(reporte['pendientes_por_llegar']) if reporte['pendientes_por_llegar'] else "  Ninguno.")

    partes.append("\n--- 🟡 CON PERMISO/AUSENCIA APROBADA ---")
    partes.append(
        formato_tabla(reporte['con_permiso'], columnas_extra='Tipo de ausencia')
        if reporte['con_permiso'] else "  Ninguno."
    )

    partes.append("\n--- ⚪ SIN HORARIO/PLANIFICACIÓN DEFINIDA ---")
    partes.append(formato_tabla(reporte['sin_horario_definido']) if reporte['sin_horario_definido'] else "  Ninguno.")

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
    fmt_cell = workbook.add_format({'border': 1})

    def escribir_hoja(nombre_hoja, filas, columnas, color_header=fmt_header):
        hoja = workbook.add_worksheet(nombre_hoja[:31])
        for col, titulo in enumerate(columnas):
            hoja.write(0, col, titulo, color_header)
        for fila_idx, f in enumerate(filas, start=1):
            hoja.write(fila_idx, 0, f['cedula'], fmt_cell)
            hoja.write(fila_idx, 1, f['nombre'], fmt_cell)
            hoja.write(fila_idx, 2, f['area'], fmt_cell)
            hoja.write(fila_idx, 3, f['entrada_esperada'], fmt_cell)
            if len(columnas) > 4:
                hoja.write(fila_idx, 4, f.get('tipo_ausencia', ''), fmt_cell)
        hoja.set_column(0, 0, 15)
        hoja.set_column(1, 1, 32)
        hoja.set_column(2, 2, 25)
        hoja.set_column(3, 3, 14)
        if len(columnas) > 4:
            hoja.set_column(4, 4, 22)

    # Nota: se dejaron fuera del Excel a propósito las hojas "Sin horario
    # definido", "Advertencias horario" y "Asistio en festivo" (decisión
    # del 2026-09-02) — esas categorías se siguen calculando y viendo en la
    # consola/log al correr manualmente, pero ya no se escriben en el
    # adjunto que recibe RH.
    columnas_base = ['Cédula', 'Nombre completo', 'Área', 'Entrada esperada']
    escribir_hoja('Inasistencias', reporte['inasistencias'], columnas_base, fmt_header)
    escribir_hoja('Aun no inicia turno', reporte['pendientes_por_llegar'], columnas_base, fmt_header_warn)
    escribir_hoja('Con permiso', reporte['con_permiso'], columnas_base + ['Tipo de ausencia'], fmt_header_ok)

    hoja_resumen = workbook.add_worksheet('Resumen')
    hoja_resumen.write(0, 0, 'Reporte de inasistencias', fmt_header)
    hoja_resumen.write(1, 0, 'Fecha evaluada:')
    hoja_resumen.write(1, 1, reporte['fecha_objetivo'].isoformat())
    hoja_resumen.write(2, 0, 'Fecha y hora de generación:')
    hoja_resumen.write(2, 1, f"{reporte['fecha_hora_texto']} ({TZ.zone})")
    hoja_resumen.write(3, 0, 'Total inasistencias:')
    hoja_resumen.write(3, 1, len(reporte['inasistencias']))
    hoja_resumen.write(4, 0, 'Total aún no inicia turno:')
    hoja_resumen.write(4, 1, len(reporte['pendientes_por_llegar']))
    hoja_resumen.write(5, 0, 'Total con permiso:')
    hoja_resumen.write(5, 1, len(reporte['con_permiso']))
    hoja_resumen.write(6, 0, 'Festivos/cierres detectados:')
    hoja_resumen.write(6, 1, ', '.join(reporte['festivos_detectados']) if reporte['festivos_detectados'] else 'Ninguno')
    hoja_resumen.write(7, 0, 'Tolerancia aplicada (min):')
    hoja_resumen.write(7, 1, TOLERANCIA_MINUTOS)
    hoja_resumen.set_column(0, 0, 30)
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
def construir_cuerpo_html(reporte):
    fecha_txt = reporte['fecha_objetivo'].strftime('%Y-%m-%d')
    total = len(reporte['inasistencias'])

    encabezado = f"""
    <h2 style="margin-bottom:4px;">Reporte de Inasistencias — {fecha_txt}</h2>
    <p style="margin-top:0;">
      <strong>Total inasistencias: {total}</strong><br/>
      Generado: {reporte['fecha_hora_texto']} ({TZ.zone})
    </p>
    """

    if reporte['festivos_detectados']:
        encabezado += (
            f'<p>📅 Festivo(s)/cierre(s) detectado(s): '
            f'{", ".join(reporte["festivos_detectados"])}</p>'
        )

    if not reporte['inasistencias']:
        return encabezado + '<p>Sin inasistencias reportadas ✅</p>'

    filas_html = ''.join(
        f"""<tr>
              <td style="border:1px solid #ddd;padding:6px;">{f['cedula']}</td>
              <td style="border:1px solid #ddd;padding:6px;">{f['nombre']}</td>
              <td style="border:1px solid #ddd;padding:6px;">{f['area']}</td>
              <td style="border:1px solid #ddd;padding:6px;">{fecha_txt}</td>
              <td style="border:1px solid #ddd;padding:6px;">{f['entrada_esperada']}</td>
            </tr>"""
        for f in reporte['inasistencias']
    )

    tabla = f"""
    <table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;">
      <thead>
        <tr style="background-color:#D9534F;color:#ffffff;">
          <th style="border:1px solid #ddd;padding:6px;text-align:left;">Cédula</th>
          <th style="border:1px solid #ddd;padding:6px;text-align:left;">Nombre completo</th>
          <th style="border:1px solid #ddd;padding:6px;text-align:left;">Área/Departamento</th>
          <th style="border:1px solid #ddd;padding:6px;text-align:left;">Fecha</th>
          <th style="border:1px solid #ddd;padding:6px;text-align:left;">Hora esperada</th>
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
    asunto = f"Reporte de Inasistencias — {fecha_txt} {hora_txt}"

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
# (wizard/alerta_inasistencias_wizard.py) y los ir.cron / Acciones de
# Servidor programadas.
#
# Se exponen 3 métodos en vez de 1 a propósito: los dos de arriba
# (_hoy / _resumen_ayer) no reciben ningún parámetro y no requieren hacer
# ningún cálculo de fecha en el código de la Acción de Servidor — así el
# código que se pega ahí es una sola línea, sin arriesgarse a que el
# sandbox de "Ejecutar código Python" rechace algo (import de timedelta,
# referencias a TZ, etc.). El tercero (sin sufijo) queda disponible para
# uso más flexible, por ejemplo desde el asistente o la shell.
# ---------------------------------------------------------------------------
class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    @api.model
    def ejecutar_alerta_inasistencias_hoy(self):
        """Para la Acción de Servidor de las alertas del día (07:00, 14:00,
        23:15). Código a pegar en la Acción de Servidor:

            env['hr.attendance'].sudo().ejecutar_alerta_inasistencias_hoy()
        """
        return self.ejecutar_alerta_inasistencias(fecha_objetivo=None)

    @api.model
    def ejecutar_alerta_inasistencias_resumen_ayer(self):
        """Para la Acción de Servidor del resumen diario (06:30), que
        evalúa el día calendario anterior completo. Código a pegar:

            env['hr.attendance'].sudo().ejecutar_alerta_inasistencias_resumen_ayer()
        """
        ayer = datetime.now(TZ).date() - timedelta(days=1)
        return self.ejecutar_alerta_inasistencias(fecha_objetivo=ayer)

    @api.model
    def ejecutar_alerta_inasistencias(self, fecha_objetivo=None, imprimir_consola=True):
        """Punto de entrada genérico (usado por el wizard y por los dos
        métodos de arriba). fecha_objetivo=None evalúa "hoy"."""
        return ejecutar_alerta_inasistencias(
            self.env, fecha_objetivo=fecha_objetivo, imprimir_consola=imprimir_consola,
        )