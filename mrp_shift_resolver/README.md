# Resolución de Turnos de Producción (`mrp_shift_resolver`)

Fase A del proyecto de OEE/tablero de piso. Sin vistas, sin menús, sin
modelos con tabla propia — cero superficie de riesgo de instalación. Solo
lógica de apoyo que consumirán `mrp_oee_report`, `mrp_oee_dashboard` y
`mrp_production_alerts`.

## Qué hace

Dado un centro de trabajo y una fecha/hora, determina a qué turno
pertenece esa hora, leyendo el `resource.calendar` asignado al centro de
trabajo (`resource_calendar_id`) — sin capturar nada nuevo, sin doble
trabajo para nadie.

## Regla de identificación (confirmada con datos reales de esta instancia)

- El **nombre** de la línea de asistencia ("Lunes Turno 3") es la única
  fuente de verdad del turno.
- `day_period` (morning/lunch/afternoon) NO se usa para identificar el
  turno — se usa solo para saber si esa franja tiene capacidad planeada.
  `lunch` = objetivo 0 (fin de semana, turno reducido apagado a propósito).
  La producción real en esa franja nunca se descarta, solo queda marcada
  como no planeada.
- El cruce de medianoche no requiere lógica especial: Odoo ya parte un
  turno que cruza medianoche en dos líneas (una por `dayofweek`) con el
  mismo nombre. Se busca por día real + hora real, nunca contra "hoy".
- Soporta calendarios versionados (`date_from`/`date_to` en las líneas):
  cada resolución usa la versión vigente en la fecha analizada.

## Instalación

1. Copiar la carpeta en el directorio de addons, push si es Odoo.sh.
2. Ajustes → Aplicaciones → Actualizar lista → instalar "Resolución de
   Turnos de Producción".

No requiere ningún paso posterior en Studio.

## Cómo probarlo (sin arriesgar nada)

Acción de servidor temporal, tipo *Ejecutar código Python*, sobre
`mrp.workcenter.productivity`, ejecutada desde la lista con varias líneas
reales seleccionadas (incluye alguna de madrugada si puedes):

```python
out = []
for rec in records:
    out.append("%s | %s | %s -> turno=%r | planeado=%s" % (
        rec.workcenter_id.name, rec.date_start, rec.date_start,
        rec.shift_name, rec.shift_is_planned))
raise UserError("\n".join(out))
```

Compara la salida contra lo que un supervisor diría a mano para esas
mismas horas. Si coincide, la Fase A queda validada y avanzamos a la
Fase B (indicadores).

## API para los módulos siguientes

```python
info = env['mrp.shift.resolver'].resolve_shift(workcenter, dt)
# info['shift_name']   -> 'Lunes Turno 3' o False
# info['is_planned']   -> True/False (False = day_period 'lunch')
# info['attendance']   -> el registro de resource.calendar.attendance

horas = env['mrp.shift.resolver'].shift_total_hours(workcenter, 'Lunes Turno 3', fecha)
# -> horas totales del turno, sumando sus líneas (incluye cruce de medianoche)
```

## Supuesto a validar

Si un centro de trabajo no tiene `resource_calendar_id` asignado,
`resolve_shift` devuelve `shift_name=False` sin error — esas líneas
quedarían sin turno identificado en los reportes de fases siguientes.
Confirmar que todas las inyectoras de Fase 1 (`tag_ids='Inyectoras'` AND
`x_studio_ct_externo=False`) tienen calendario asignado antes de construir
la Fase B.

---

## Cambios v18.0.1.1.0 — campos almacenados + fecha operativa

**1. `shift_name` y `shift_is_planned` pasan a almacenados (`store=True`).**
Dos razones:
- La Fase B (vista SQL de OEE) agrupa por turno, y SQL no puede leer
  campos calculados no almacenados.
- Integridad histórica: al quedar grabado, un cambio futuro de calendario
  no reescribe el turno de registros ya cerrados.

**2. Campo nuevo `shift_date` (Fecha Operativa).** Día en que ARRANCÓ el
turno. Una línea de las 02:00 del martes que pertenece a "Lunes Turno 3"
tiene fecha operativa del **lunes**. Sin este campo, el OEE diario del
lunes perdería su propio turno nocturno y se lo sumaría al martes.

Regla de detección, deliberadamente estructural (no parsea nombres de
días): si la línea de asistencia encontrada empieza a las 00:00 y existe
otra línea del mismo turno que termina a las 24:00, es la continuación
tras medianoche → el turno arrancó el día anterior.

Se evitó ordenar por `dayofweek` para deducirlo porque "Domingo Turno 3"
abarca dayofweek 6 y 0: al cruzar de semana, el menor dayofweek daría el
día equivocado. Verificado contra ese caso concreto.

## ATENCIÓN al actualizar

Al pasar los campos a almacenados, Odoo recalcula **todos** los registros
históricos de `mrp.workcenter.productivity` durante la actualización del
módulo. En una tabla con muchos miles de líneas esto puede tardar varios
minutos, durante los cuales la base queda ocupada.

**Recomendación**: actualizar en un momento de baja actividad y avisar a
las otras personas que comparten el ambiente de test.

## Validación posterior a la actualización

Además de verificar el turno (script del apartado anterior), confirmar la
fecha operativa en una línea de madrugada:

```python
Productivity = env['mrp.workcenter.productivity'].sudo()
lineas = Productivity.search(
    [('shift_name', 'like', 'Turno 3')], order='date_start desc', limit=15)
out = []
for rec in lineas:
    out.append("%s | %s UTC | turno=%r | fecha_operativa=%s | planeado=%s" % (
        rec.workcenter_id.name, rec.date_start, rec.shift_name,
        rec.shift_date, rec.shift_is_planned))
raise UserError("\n".join(out) or "Sin lineas de Turno 3.")
```

En una línea de madrugada, `fecha_operativa` debe ser el día ANTERIOR a la
fecha del `date_start` en hora local.
