# OEE por Turno y Tablero OEE (`mrp_oee_report`) — 18.0.1.3.0

## 1.3: actualizar sin afectar a otros usuarios

| Momento | 1.2 | 1.3 |
|---|---|---|
| Actualizar el módulo | Recreaba la vista con TODO el histórico dentro de la actualización (30 s a 1 min, crece con los años) | No recalcula nada si el cálculo no cambió (huella `mrp_oee_report.calc_hash`). Si cambió, solo marca el histórico como pendiente; la actualización sigue tomando segundos |
| Cada 15 min / botón Actualizar | Recalculaba todo el histórico (13 s con un año de 30 máquinas) | Solo los últimos 3 días (`mrp_oee_report.recalc_days`): 0,25 s con 290.000 líneas |
| Histórico cuando cambia el cálculo | — | Acción programada "OEE: recalcular histórico en segundo plano", mes a mes de lo reciente a lo antiguo, commit entre pasos (~1 s por mes); el tablero muestra el avance |
| Correcciones de más de 3 días | — | Botón "Recalcular periodo" (fechas del filtro, máx. 13 meses por clic) |

Los datos viven en una tabla normal (`mrp_oee_line`); los recálculos son DELETE + INSERT por rango con un candado propio (`pg_advisory_xact_lock`), así que nunca bloquean a los usuarios de otros módulos ni a quien está mirando el tablero.

## Versión 1.2 (base del cálculo)

Solo Odoo 18 (decisión del 21/10/2026; la rama 19 queda en 19.0.1.1.0 sin estos cambios).

## Qué cambió frente a 18.0.1.1.0 (feedback de planta, 21/10)

| Tema | 1.1 | 1.2 |
|---|---|---|
| Línea que cruza turnos | Contaba completa en el turno donde empezó | Se reparte entre los turnos que atraviesa; minutos y piezas en proporción |
| Línea olvidada abierta | Inflaba el día (INY1 15/10: 194 h) | Más de 12 h: no cuenta en el OEE y aparece en Calidad del registro |
| Varias OT a la vez en la misma máquina | Se sumaba el reloj varias veces | El reloj se cuenta una vez. Una parada registrada gana sobre "operando"; entre órdenes operando, el tiempo se reparte en partes iguales. No aplica en CT con etiqueta del parámetro `mrp_oee_report.parallel_tags` (por defecto "Terminado & Empaque") |
| Duración de turnos | Solo turnos donde empezaba alguna línea (INY1: 16 h) | Todos los turnos del calendario del día, regla de `mrp_shift_resolver`: por nombre, con vigencia, sin franjas "Descanso"; hoy, solo hasta la hora actual |
| % de la cascada | Contra la barra más larga | Base 100% = turnos planeados (+ turnos extra con registro). Filtrando OP, producto u operario, la base es su tiempo registrado |
| Ciclo estándar | Teórico | Actual; si está vacío, teórico; sin molde, `time_cycle_manual` de la operación. La eficiencia del CT no se aplica |
| Pareto de defectos | Fecha y máquina; campos adivinados | Campos de `mrp.averia.report` (`categoria_id`, `cantidad`, `shift_date`, `workcenter_id`, `production_id`, `product_id`, `shift_name`) con los mismos filtros |
| OEE sobre 100% | Verde | "Revisar datos" (rayado) |
| Datos | En vivo | Recalculados cada 15 min y con el botón Actualizar; muestra "Datos al" (en 1.3: tabla por partes) |
| Nueva pestaña | — | **Calidad del registro**: líneas olvidadas, traslapes, turnos con más de 30 min sin registro, órdenes con producción registrada < 90%, Rendimiento > 105% u operando sin piezas |

## Cálculo

```
registrado = operando + autorizada + no programada   (repartido por turno, sin traslapes)
cargado    = registrado - autorizada
D   = operando / cargado
R   = (buenas + averías) x min estándar por pieza / min operando con estándar
C   = buenas / (buenas + averías)
OEE = D x R x C
min estándar por pieza = ciclo (s) / cavidades / 60
tiempo perdido en averías = averías x min estándar por pieza
"habría dado N unidades más" = minutos de la mayor pérdida / (min valiosos / buenas)
```

Operando = motivos de categoría Productivo, Rendimiento o Calidad. Autorizada = casilla en el motivo. No programada = Disponibilidad o sin categoría.

## Validación

- Odoo 18 limpio (código oficial 18.0): instalación, actualización sobre 1.1, vistas, menús, acción programada y tablero en navegador real sin errores de consola.
- Escenario con las 27 líneas reales de INY1 del 15 al 17/10: 24:00 h de turnos el 15/10; ningún turno pasa de 8 h; la línea de 150 h queda como olvidada.
- Volumen (1.3): 290.000 líneas (30 máquinas, un año): refresco de 3 días 0,25 s; histórico completo en segundo plano 12 s en 13 pasos.
- Actualización 1.2 → 1.3 en el Odoo de prueba: 4,7 s incluyendo el arranque de Odoo; una segunda actualización sin cambios no recalcula nada.

## Después de actualizar

1. Marcar "Parada autorizada" en los motivos que aplique (purga, despeje de línea, parada programada, mantenimiento preventivo, refrigerio...).
2. Confirmar en planta si "Terminado & Empaque" es el único grupo con OT en paralelo; cambiarlo en Ajustes → Técnico → Parámetros del sistema → `mrp_oee_report.parallel_tags` y pulsar Actualizar.
3. Al pasar de 1.1 o 1.2 a 1.3 la actualización toma segundos; el histórico se completa solo en segundo plano y el tablero lo indica mientras termina.
