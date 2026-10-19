# OEE por Turno y Tablero OEE (`mrp_oee_report`)

Versiones: **18.0.1.1.0** (Odoo 18) y **19.0.1.1.0** (Odoo 19), mismo código salvo el número de versión.

## Qué cambió frente a 18.0.1.0.0

| # | Antes | Ahora |
|---|---|---|
| 1 | D = productivos / totales: setup y purga restaban Disponibilidad | Casilla **Parada autorizada** en el motivo de pérdida; esas horas salen antes (tiempo cargado), como en Access |
| 2 | Estándar con ciclo ACTUAL del molde | Ciclo **TEÓRICO** del molde (el actual solo si el teórico está vacío) |
| 3 | Unidades teóricas solo en líneas productivas → R > 100% si la cantidad se reporta en una línea de parada | R = minutos estándar de lo producido / minutos operando, independiente de la línea donde se reportó |
| 4 | Los % se sumaban al agrupar en pivot/lista | % sin agregación; consolidados en el Tablero, siempre sobre sumas de minutos |
| 5 | Base = minutos registrados | El Tablero muestra además la duración de turnos (calendario) y el tiempo **sin registrar** |
| 6 | `l.loss_type` — no existe en Odoo 19 (no almacenado) | Categoría leída de `mrp_workcenter_productivity_loss_type`: funciona en 18 y 19 |
| 7 | Semáforo fijo 80/70 | Meta = `oee_target` del centro de trabajo; verde ≥ meta, amarillo hasta 10 puntos debajo, rojo más abajo |
| 8 | `unidades / unidades` en SQL daba división entera | Cantidades convertidas a decimal |

## Modelo de minutos

```
registrado = operando + paradas autorizadas + paradas no programadas
cargado    = registrado - paradas autorizadas
D   = operando / cargado
R   = (unidades buenas + averías) x minutos estándar por unidad / minutos operando con estándar
C   = buenas / (buenas + averías)
OEE = D x R x C
```

Clase de tiempo de cada línea según su motivo:

| Motivo | Clase |
|---|---|
| Casilla "Parada autorizada" marcada | Autorizada |
| Categoría Productivo, Rendimiento o Calidad (máquina corriendo) | Operando |
| Categoría Disponibilidad, o sin categoría | No programada |

Minutos estándar por unidad: ciclo teórico del molde (seg) ÷ cavidades ÷ 60; si no hay molde, `time_cycle_manual` de la operación. Las líneas sin ninguno de los dos no entran al Rendimiento y el Tablero lo avisa.

Validado con el caso del 21/09 del tablero de Access (PostgreSQL 16, esquemas 18 y 19): D 97,0 · R 84,8 · C 94,7 · OEE 77,9, velocidad 15:46 h, calidad 4:42 h — idéntico. La fórmula anterior daba 67,6 con los mismos datos.

## Menús

- Fabricación → Informes → **Tablero OEE** (pantalla de planta)
- Fabricación → Informes → **OEE por Turno** (lista / pivot de minutos)
- Fabricación → Informes → **Líneas de OEE** (detalle por línea de tiempo)
- Fabricación → Configuración → **Motivos de pérdida (OEE)** (casilla Parada autorizada)

## Tablero

Filtros: Hoy / Ayer / 7 días / 30 días / Mes / Rango, grupo de CT (etiqueta), máquina, turno, búsqueda por OP, producto u operario, solo turnos planeados, h:mm o minutos.

Bloques: OEE con D/R/C y meta · cumplimiento del plan (prorrateo de las órdenes de trabajo programadas), horas de setup · tasa de scrap y no conformes · paradas no programadas, eventos y microparadas (< 5 min) · cascada "En qué se fueron los minutos" · máquinas que más tiempo perdieron · OEE por turno · Paretos de paradas no programadas, autorizadas y defectos (si está instalada la tipificación de averías) · tabla Máquinas / Órdenes / Productos / Operarios con uso del tiempo, plan % y costo del tiempo perdido (`costs_hour`).

## Después de instalar

1. Fabricación → Configuración → Motivos de pérdida (OEE): marcar **Parada autorizada** en los motivos de setup / cambio / purga (hoy: "Configuración y ajustes"; decidir "movimiento de maquina", que no tiene categoría).
2. Revisar `oee_target` de los CT: hoy todos están en 90.
3. Si se actualiza `mrp_shift_resolver` o `mrp_mold_management`: OEE por Turno → Acciones → **Regenerar informe de OEE**.

## Trampas que se evitaron

Sin herencia de vistas existentes (lista propia para motivos de pérdida); menús ubicados por `<function>` sin `noupdate`; columnas opcionales verificadas en `information_schema` antes de crear la vista.
