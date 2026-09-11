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

---

## Cambios v18.0.1.3.0 — vínculo uno a uno, sin búsqueda ambigua

**Rediseño según caso real confirmado**: PR Mug X (padre, operación Soplar
con su molde) + ST Inyectar Mug (hija, operación Inyectar con su propio
molde) — cada operación de cada LdM tiene su propio molde, de forma directa.

**Antes**: el molde declaraba una lista de operaciones calificadas
(Many2many), y la orden de trabajo buscaba entre los moldes compatibles
esperando encontrar exactamente uno sin ambigüedad.

**Ahora**: cada operación de la LdM (`mrp.routing.workcenter`) tiene su
propio campo **Molde** (`mold_id`), uno a uno. La orden de trabajo ya no
busca nada — copia el molde directo de la operación de la que proviene
(`operation_id.mold_id`). Cero ambigüedad posible, porque el diseño ya no
permite que exista.

**Bono**: al ser un campo Many2one normal, "Crear y editar..." para dar de
alta un molde nuevo sin salir de la LdM ya viene incluido de fábrica — no
hizo falta construir nada aparte para eso.

**En el molde**, `qualified_operation_ids` pasa de lista editable a lista de
solo lectura (qué operaciones lo usan hoy) — se edita desde la operación,
no desde el molde, para que exista un solo lugar donde se establece el
vínculo.

**Sin cambios**: la propagación del ciclo al aplicar una revisión (botón
"Aplicar al Molde") sigue funcionando igual — ahora lee la misma
información, solo que a través del vínculo uno a uno en vez de la lista
calificada.

## Pendiente, confirmado como NO urgente (mismo campo, no otro modelo)

Que el campo nativo de duración de la operación se vuelva de solo lectura y
muestre el mismo ciclo en segundos por unidad cuando hay un molde vinculado.
Es una mejora de vista sobre el mismo `mold_id` construido en esta versión,
no un modelo nuevo — queda para una siguiente iteración, junto con el
objetivo por turno y el ensamblaje de OEE (temas deliberadamente fuera de
esta entrega para no mezclarlos).

---

## Cambios v18.0.1.4.0 — corrección de fondo del problema de menús

**Causa raíz confirmada**: `post_init_hook` solo se ejecuta en la primera
instalación de un módulo, nunca en una actualización. Como este módulo
siempre se despliega reemplazando la carpeta y actualizando (nunca
reinstalando desde cero), la lógica de reubicar menús jamás se había
ejecutado en ninguna versión anterior — no era un bug puntual, era un
mecanismo incompatible con la forma real de desplegar.

**Corrección**: la misma lógica (buscar el submenú "Equipos" por nombre bajo
la raíz de Mantenimiento, sin depender de ningún xml_id externo) ahora vive
en un modelo abstracto (`models/setup.py`) invocado desde
`data/menu_placement.xml` con un `<function>`. Los archivos de datos SIN
`noupdate` se re-ejecutan en cada actualización del módulo, así que esto se
corrige solo cada vez que actualices, sin depender de una reinstalación.

Se quitó `post_init_hook` del manifest — ya no hace falta, el archivo de
datos cubre tanto la instalación como cualquier actualización futura.

## Pendiente, esta vez a propósito y explícito

El campo `mold_id` de `mrp.routing.workcenter` sigue sin vista propia en el
módulo. Ya hubo dos intentos fallidos de adivinar un xml_id de vista en este
proyecto (uno de ellos tumbó el ambiente completo); antes de un tercer
intento a ciegas, se solicitó el xml_id real de las vistas de
`mrp.routing.workcenter` mediante un diagnóstico de solo lectura. La vista
se construye en la siguiente versión, con el dato confirmado en vez de una
suposición.

---

## Cambios v18.0.1.4.1

`mold_id` (en la operación de LdM y en la orden de trabajo) ahora crea el
equipo nuevo con `is_mold` marcado automáticamente desde "Crear y editar...".
Sin esto, un molde creado desde ahí nacía con la pestaña de cavidades/ciclo
oculta, porque esa pestaña solo se muestra si `is_mold` está tildado — la
persona tendría que descubrir que hay que marcar la casilla antes de poder
cargar los datos. Ahora aparece de inmediato.

Cambio hecho a nivel de campo (Python), no de vista: no depende del xml_id
de `mrp.routing.workcenter` que sigue pendiente de confirmar, así que no
tiene el riesgo de las vistas heredadas y se puede desplegar ya.

**Sigue pendiente**: la vista que efectivamente coloca `mold_id` en el
formulario emergente de Operaciones de la LdM. Bloqueado hasta confirmar
el xml_id real (diagnóstico solicitado, aún sin respuesta).

---

## Cambios v18.0.1.5.0 — campo Molde ya en la Lista de Materiales

Con el xml_id confirmado por diagnóstico en vivo (no una suposición), el
campo `mold_id` ahora aparece directamente en el formulario "Abrir:
Operaciones" de la pestaña Operaciones de cualquier LdM, justo después de
Centro de Trabajo. Ya no requiere ningún paso manual en Studio.

Vista base confirmada: `mrp.mrp_routing_workcenter_form_view` (sin padre).
Las extensiones de `mrp_workorder` y de Studio en esta instancia heredan de
esa misma base de forma independiente entre sí, así que esta tercera
extensión se combina con ellas sin conflicto.

**Si ya habías agregado el campo manualmente por Studio** mientras
esperabas esta confirmación, revisa que no quede duplicado en la vista —
quítalo desde Studio para que solo quede la versión que trae el módulo.

---

## Corrección v18.0.1.5.1

El atributo `context` de un campo relacional en Python debe ser un
**diccionario**; la forma de texto (`context="{'default_is_mold': True}"`)
solo es válida como atributo en XML. Odoo intentaba expandir ese string con
`**` y fallaba al abrir el formulario de Operaciones:

    TypeError: with_context() argument after ** must be a mapping, not str

Corregido a `context={"default_is_mold": True}` en `mrp.routing.workcenter`
y en `mrp.workorder`. Mismo comportamiento previsto (el molde nuevo nace
marcado como molde), ahora en la forma que el ORM espera.
