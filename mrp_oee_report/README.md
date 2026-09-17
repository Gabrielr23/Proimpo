# Informe de OEE por Turno (`mrp_oee_report`)

Fase B del proyecto de OEE/tablero de piso. Vista SQL de solo lectura.
**Grano: centro de trabajo × fecha operativa × turno.**

`depends`: `mrp`, `mrp_shift_resolver`, `mrp_mold_management`

## Por qué reemplaza a `mrp_averias_report`

Aquel informe ancla solo en horas CON avería, así que su universo está
sesgado y sus denominadores no sirven (producción total, tiempo total).
Este ancla en TODAS las líneas de `mrp.workcenter.productivity`.

## Fórmulas

| Indicador | Cálculo |
|---|---|
| Disponibilidad | minutos productivos / minutos totales |
| Rendimiento | (buenas + averías) / unidades teóricas |
| Calidad | buenas / (buenas + averías) |
| OEE | Disponibilidad × Rendimiento × Calidad |

Escala 0-100. Semáforo: **verde ≥80 · amarillo 70-80 · rojo <70**.

## Objetivo por hora — cadena de respaldo

Se calcula **por línea**, no por turno (un turno puede correr varias
órdenes distintas):

1. Molde de la orden u operación: `3600 / (ciclo efectivo / cavidades)`
2. Ciclo manual de la operación: `60 / time_cycle_manual`

El tercer nivel de respaldo que existe en Python (`duration_expected /
qty_production`) **no se pudo replicar en SQL**: `qty_production` es
`store=False` y las vistas SQL solo leen columnas almacenadas. Igual
motivo por el que se usa `time_cycle_manual` y no `time_cycle`.

## Reglas de cálculo que vale la pena conocer

**Las unidades teóricas solo se acumulan en tiempo PRODUCTIVO.** Exigirle
producción a una máquina detenida por una parada ya registrada castigaría
dos veces la disponibilidad.

**Y solo en turnos PLANEADOS.** En una franja con `day_period='lunch'`
(capacidad apagada por diseño) el objetivo es 0, así que:
- la producción real SÍ se reporta (cantidad, averías, Calidad,
  Disponibilidad);
- Rendimiento y OEE quedan **en blanco**, no en cero — no se juzga contra
  una meta que no existía.

Filtro "Turno extra / no planeado" en la búsqueda para aislar esos casos.

## Validación hecha antes de entregar

Se levantó PostgreSQL 16, se replicó el esquema real y se verificó la
aritmética a mano:

| Caso | Resultado esperado | Obtenido |
|---|---|---|
| Molde 2 cav/30s, 2h productivas + 1h parada, 420 buenas + 30 averías | Disp 66,7 · Rend 93,8 · Cal 93,3 · OEE 58,3 | idéntico |
| Operación SIN molde, ciclo manual 0,5 min/ud, 2h, 200+40 | Disp 100 · Rend 100 · Cal 83,3 · OEE 83,3 | idéntico |
| Turno no planeado (domingo) con producción real | cantidad visible, Rend y OEE en blanco | idéntico |

## Instalación

Requiere `mrp_shift_resolver` **v18.0.1.1.0 o superior** instalado (los
campos `shift_name`, `shift_date` y `shift_is_planned` deben estar
almacenados). Si `shift_is_planned` no existiera, el módulo lo detecta y
asume todos los turnos planeados, dejando una advertencia en el log.

Menú: **Fabricación → Informes → OEE por Turno** (ubicado por
`data/menu_placement.xml`, que se reejecuta en cada actualización).

## Mantenimiento

Si se agregan columnas o cambia la estructura, regenerar la vista con
⚙ Acciones → **Regenerar informe de OEE** desde la vista de lista, sin
necesidad de actualizar el módulo.

## Pendiente para Fase C (`mrp_oee_dashboard`)

- Consolidado por máquina-día (agrupando los 3 turnos) y de planta,
  **ponderado por horas de operación** — no se puede hacer con un pivot
  normal, porque promediar porcentajes ya calculados da un número
  distinto al correcto.
- Filtro de alcance Fase 1: `tag_ids='Inyectoras'` AND
  `x_studio_ct_externo=False`.
- Drill-down: día → máquina → turno.
