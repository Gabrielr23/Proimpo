# Resolución de Turnos de Producción (`mrp_shift_resolver`) — Odoo 19

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
- **Odoo 19 ya no tiene `date_from`/`date_to` en las líneas de asistencia**,
  así que no hay versionado de horarios por línea. El histórico se protege
  porque el turno queda grabado en cada registro de tiempo.

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

## Diferencias frente a la versión 18.0.1.1.0

| Tema | Odoo 18 | Odoo 19 |
|---|---|---|
| Vigencia de líneas | `date_from`/`date_to` | **No existen**: se usan todas las líneas del calendario |
| Secciones de la vista | no se filtraban | se ignoran (`display_type`) |
| `day_period` | morning / lunch / afternoon | además `full_day`; la regla sigue igual: `lunch` = no planeado |

Los campos `shift_name`, `shift_date` y `shift_is_planned` son los mismos,
almacenados, en `mrp.workcenter.productivity`.

## Cómo cambiar horarios en Odoo 19

Ya no se pueden crear líneas nuevas con fecha de inicio. Para un cambio de
horario: editar el calendario del centro de trabajo (o asignarle uno nuevo).
Lo ya registrado conserva su turno porque está almacenado. Solo se vuelve a
calcular un registro si se edita su centro de trabajo o su fecha de inicio.

## Limitación conocida

Calendarios en modo "2 semanas" (`week_type`): no se distingue la semana; se
consideran las líneas de ambas. Los calendarios de planta usan una sola
semana.

## ATENCIÓN al instalar

- **Base migrada desde Odoo 18 con la versión 1.1.0 ya instalada**: actualizar
  el módulo, no reinstalarlo. Las columnas ya existen con sus valores.
- **Base nueva o sin el módulo previo**: Odoo calcula el turno de TODAS las
  líneas históricas de `mrp.workcenter.productivity` al instalar. Puede tardar
  varios minutos; hacerlo en baja actividad.

## Validación posterior

Mismo script de la versión 18 (sección anterior): en una línea de madrugada,
`fecha_operativa` debe ser el día ANTERIOR a la fecha local del `date_start`.
