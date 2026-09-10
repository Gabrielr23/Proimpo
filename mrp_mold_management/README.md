# Gestión de Moldes de Inyección (`mrp_mold_management`)

Modela el molde como una extensión de `maintenance.equipment` — no como un
modelo paralelo — para heredar de forma nativa el calendario de mantenimiento
preventivo, las solicitudes correctivas, el técnico asignado y las
categorías, sin reconstruir ese sistema.

## Qué añade

**En `maintenance.equipment`** (pestaña "Especificaciones de Molde", visible
solo si `is_mold` está marcado):

| Campo | Uso |
|---|---|
| Cavidades Actuales | cambia por desgaste/mantenimiento |
| Ciclo Teórico / Ciclo Actual | segundos por disparo |
| Objetivo por Hora | computado: `3600 / (ciclo actual / cavidades)`, en vivo |
| Peso Estándar Pieza | gramos |
| Centros de Trabajo Compatibles | Many2many, sin orden de prioridad |
| LdM Calificadas | Many2many a `mrp.bom` |

**Modelo nuevo `mrp.mold.revision.log`** — misma estructura que el control
manual existente (fecha, cavidades/ciclo verificados, análisis, acción,
responsable, fecha de ejecución, cumple, observaciones). El botón
**Aplicar al Molde** traslada los valores verificados a las cavidades/ciclo
vigentes; es manual a propósito, para que un responsable confirme antes de
que cambie el objetivo de producción de toda la línea.

**En `mrp.workorder`**: campo `Molde`, filtrado por centros de trabajo
compatibles, y el objetivo por hora resultante junto a la duración esperada.

## Instalación

1. Copiar la carpeta en el directorio de addons y hacer push si es Odoo.sh.
2. Ajustes → Aplicaciones → Actualizar lista de aplicaciones.
3. Instalar "Gestión de Moldes de Inyección".
4. Menús en **Mantenimiento → Moldes** y **Mantenimiento → Bitácora de
   Revisión de Moldes**.

## Riesgo conocido de instalación

Las vistas de equipo de mantenimiento se extienden referenciando los xml_id
`maintenance.hr_equipment_view_form`, `..._tree` y `..._search` (nombres
heredados de versiones anteriores del módulo). Si tu instancia los tiene con
otro nombre, la instalación fallará con "vista no encontrada". Para
confirmar los nombres reales: Ajustes → Técnico → Interfaz de usuario →
Vistas, filtrar por modelo `maintenance.equipment`. Si difieren, envía los
xml_id correctos y se ajusta en un minuto.

Mismo riesgo, menor probabilidad, en `mrp.mrp_workorder_view_form`
(la vista de formulario de Orden de Trabajo).

## Qué falta a propósito (siguiente iteración)

- **Validación de choque de horario**: hoy nada impide que dos órdenes de
  trabajo reclamen el mismo molde en horarios solapados. Se deja para
  después de validar que esta primera entrega funciona en la instancia real.
- **Peso real vs. receta**: pendiente de definir dónde captura (según lo
  conversado, muestreo único al liberar la orden — encaja como control de
  calidad puntual, no como parte de este módulo).
- **Tablero en tiempo real y alertas** (Fase 1): consume el `hourly_target`
  de este módulo más el calendario de turnos ya existente
  (`resource.calendar` "Horario CT Inyectoras L-S") y `x_studio_fecha_despacho`
  como definición de retraso. Es la siguiente entrega.

---

## Cambios v18.0.1.1.0

**Menú.** "Moldes" ahora se busca por nombre y se cuelga dentro del submenú
**Equipos** (junto a Centros de trabajo y Máquinas y herramientas) en lugar
de quedar como ítem separado. La bitácora se renombra a **"Actualización de
Especificaciones de Molde"** y queda aparte, bajo la raíz de Mantenimiento:
es una actividad de ingeniería de proceso (ajustar la línea base de
cavidades/ciclo), no un ticket de reparación — por diseño no vive dentro de
Equipos.

**Asignación automática de molde.** Al crearse una orden de trabajo, si
existe un único molde activo, compatible con el centro de trabajo y
calificado para la LdM de la orden, se asigna solo. Si hay cero o varios
candidatos, queda en blanco: esa ambigüedad la resuelve el planeador
(disponibilidad, fecha de entrega, o si el molde ya está montado).

**Duración de planeación vs. molde real.** `duration_expected` (el campo
nativo que alimenta el Gantt) se calcula una sola vez, al crear la orden,
con el ciclo estático de la ruta — no se entera de cambios posteriores en
el molde. Se añadió:

- `mold_duration_expected`: lo que debería durar la orden con el ciclo y
  cavidades REALES del molde asignado. Solo informativo, se recalcula solo.
- Botón **"Aplicar duración del molde"** (agregar vía Studio, ver comentario
  en `views/mrp_workorder_views.xml`): sobrescribe `duration_expected` con
  ese valor. Deliberadamente manual — no automático — porque ese campo
  alimenta fechas comprometidas de la MO y un error de fórmula ahí es más
  costoso que en un campo informativo.
- Al aplicar una revisión de molde que cambia cavidades/ciclo, el aviso
  ahora indica cuántas órdenes pendientes usan ese molde, para que el
  planeador decida cuáles recalcular. No las toca solas.

## Importación masiva de moldes

No requiere ID externo. En el asistente de importación, la columna mapeada
a "Centros de Trabajo Compatibles" acepta los nombres directamente,
separados por coma (`Inyectora 1,Inyectora 3,Inyectora 5`); Odoo los
resuelve por nombre. El ID externo solo es necesario si hay dos registros
con el nombre exactamente igual.

## Pendiente, sin construir todavía (requiere tu confirmación)

Actualizar el `time_cycle` de la ruta/LdM cuando cambia el molde, para que
las órdenes que **todavía no existen** también planeen con el dato correcto
desde el momento en que se crean. No se implementó porque una ruta puede,
en teoría, estar calificada para más de un molde con ciclos distintos —
sobrescribirla a ciegas podría ser incorrecto en ese caso. Si en la práctica
cada ruta tiene siempre un único molde calificado, es una extensión sencilla
del mismo mecanismo ya construido.

---

## Cambios v18.0.1.2.0 — corrección de la LdM, no solo de la orden

**El problema que resuelve esta versión.** Las versiones anteriores corregían
`duration_expected` orden por orden, con un botón manual. Eso significaba que
cada MO nueva de un producto cuyo molde cambió seguía naciendo con el ciclo
viejo — trabajo repetido sin fin. Esta versión corrige la **fuente**: la
operación de la ruta (LdM), para que las órdenes nuevas nazcan bien solas.

**Campo reemplazado.** `qualified_bom_ids` (LdM completa) se reemplaza por
`qualified_operation_ids`, que apunta a la **operación exacta** de la ruta
(`mrp.routing.workcenter`). Hace falta ese nivel de precisión porque es el
registro que efectivamente hay que corregir (`time_cycle_manual`), no la LdM
en abstracto.

**Cuándo se propaga.** Automáticamente al pulsar "Aplicar al Molde" en la
bitácora — el mismo momento en que un responsable ya confirmó que el cambio
es real.

**Modo de tiempo de la operación.** `mrp.routing.workcenter` tiene un modo
`manual` o `automático` (Odoo recalcula el ciclo solo desde el histórico en
modo automático, ignorando cualquier valor escrito). Si la operación está en
automático, el aviso al aplicar la revisión lo dice explícitamente — de lo
contrario el cambio no tendría ningún efecto y nadie lo notaría.

**Apagar este mecanismo.** Parámetro de sistema
`mrp_mold_management.push_cycle_to_routing` (Ajustes → Técnico → Parámetros
del sistema). Poner `False` lo desactiva sin tocar código. Hágalo el día que
el ajuste de LdM pase a gestionarse por PLM, para que este mecanismo no
escriba por debajo de ese flujo de aprobación — en ese momento se puede
convertir en "generar una Orden de Cambio de Ingeniería" en vez de escribir
directo.

**Lo que sigue igual.** El botón "Aplicar duración del molde" por orden de
trabajo sigue siendo necesario para las órdenes que **ya existían** antes de
la revisión y aún no han iniciado: esas nacieron con el dato viejo y no se
autocorrigen solas. Es el único punto donde queda un paso manual, y es
inevitable — el registro ya existe con un número guardado.
