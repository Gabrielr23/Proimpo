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

---

## Corrección v18.0.1.5.2 — moldes invisibles en el desplegable

El dominio exigía que el molde tuviera el centro de trabajo de la operación
en su lista de Centros Compatibles. Consecuencia no prevista: un molde
recién creado (que aún no tiene esa lista llena) quedaba invisible en el
mismo desplegable desde donde se acababa de crear.

Ahora el dominio también acepta moldes SIN compatibilidad definida:

    [('is_mold','=',True),
     '|', ('compatible_workcenter_ids','=',False),
          ('compatible_workcenter_ids','=',workcenter_id)]

Aplicado en `mrp.routing.workcenter` y en `mrp.workorder`. Una vez que se
llenan los Centros Compatibles de un molde, el filtro vuelve a aplicar con
normalidad para ese molde.

---

## Cambios v18.0.1.6.0

**1. Ciclo Efectivo (respaldo automático).** `hourly_target` daba 0 cuando
el molde tenía Ciclo Teórico informado pero Ciclo Actual en 0 — el caso de
todo molde recién creado. Se añadió `cycle_time_effective`: usa el Ciclo
Actual si está informado, y si no, el Ciclo Teórico. Todos los cálculos
(objetivo por hora, duración por molde, propagación a la ruta) pasan a usar
ese campo. Con cavidades 2 y ciclo teórico 30 seg: 240 unidades/hora.

**2. La duración nativa de Odoo se actualiza al elegir molde.** `onchange`
sobre `mold_id`: pone el modo de tiempo en manual y escribe
`time_cycle_manual` = (ciclo efectivo / cavidades) / 60 — es decir, tiempo
por UNA unidad. Si el molde se deja vacío, la duración nativa NO se toca
(se respeta lo que el facilitador haya puesto a mano). No se dejó de solo
lectura, como se acordó.

**3. Datos del molde visibles en la operación.** Campos de solo lectura
`mold_cavity_count`, `mold_cycle_time` y `mold_hourly_target`, para ver
cavidades y ciclo sin abrir la ficha del molde.

**4. Columna Molde en la tabla de Operaciones de la LdM.** El formulario
emergente "Abrir: Operaciones" NO usa el formulario base del modelo — se
comprobó en vivo que el campo aparece en Configuración → Operaciones pero
no en el emergente, lo que indica que ese emergente se define en otro lugar
aún sin identificar. Como alternativa funcional, la columna se agregó a la
tabla misma (`mrp.mrp_routing_workcenter_bom_tree_view`, xml_id confirmado),
con un ancla `//list` que no asume nada sobre las demás columnas.

## IMPORTANTE: por qué el desplegable seguía vacío

El molde "Molde Preforma 7543" tiene como Centros de Trabajo Compatibles
**Inyectora7 e Inyectora8**, pero la operación de la LdM usa **Inyectora9**.
El dominio filtra correctamente y por eso no aparece. La relajación de
v1.5.2 solo cubre moldes con la lista VACÍA; una vez que la lista tiene
valores, el filtro aplica.

Para que ese molde aparezca en esa operación: agregar Inyectora9 a sus
Centros de Trabajo Compatibles (o vaciar la lista si el molde sirve en
cualquier inyectora).

---

## Cambios v18.0.1.7.0

**Objetivo por hora universal (`hourly_target`).** Antes el objetivo estaba
atado exclusivamente al molde, dejando sin objetivo a las operaciones que no
lo usan (empaque, alistamiento, impresión). Ahora hay cadena de respaldo:

| Nivel | Fuente | Fórmula |
|---|---|---|
| 1 | Molde | ciclo efectivo / cavidades |
| 2 | Ciclo de la operación | 60 / time_cycle |
| 3 | Duración esperada | qty_production / (duration_expected / 60) |

Disponible en `mrp.routing.workcenter` (niveles 1-2) y en `mrp.workorder`
(los tres niveles). Toda operación y toda orden tienen objetivo, con molde
o sin él.

## CAUSA RAÍZ del emergente "Abrir: Operaciones"

Diagnóstico en vivo del arch de `mrp.bom`:

- `mrp.mrp_bom_form_view` define `operation_ids` SIN subvistas propias, solo
  con `list_view_ref` en contexto.
- `studio_customization.odoo_studio_mrp_bom__df4d4a76-...` inyecta subvistas
  EN LÍNEA dentro de ese campo (`position="inside"` con un `<list>`
  completo).

Cuando Studio edita un one2many, congela una copia del arch resuelto en ese
momento y la guarda en línea. Esa copia deja de recibir herencia del modelo.
De ahí que el emergente muestre la pestaña "Work Sheet" (existía al momento
de la foto) pero nunca el campo Molde (añadido después).

**Implicación**: la columna que v1.6.0 agregó a
`mrp.mrp_routing_workcenter_bom_tree_view` tampoco se ve, porque el `<list>`
en línea de Studio pisa el `list_view_ref`. Se deja en el módulo porque SÍ
funciona en bases sin esa personalización de Studio.

**Por qué NO se resuelve desde el módulo**: el único punto donde se puede
insertar el campo es la subvista en línea de Studio, cuyo xml_id contiene un
UUID aleatorio distinto en cada base de datos. Un módulo que dependa de ese
xml_id fallaría al instalarse en cualquier otra instancia (producción, la
otra base de test), tumbando el registro completo — riesgo ya materializado
una vez en este proyecto.

**Solución**: agregar el campo desde Studio, una vez por base de datos, con
el emergente abierto. Studio lo insertará en su propia subvista en línea,
que es donde corresponde.

## Pendiente: objetivo por turno

Requiere definir la duración del turno. El calendario existente
("Horario CT Inyectoras L-S") tiene turnos de distinta duración: T1 6:00-13:00
(7 h), T2 13:00-21:30 (8,5 h), T3 21:30-6:00 (8,5 h). Sin decidir si el
objetivo por turno debe ser por turno específico o con una duración única
parametrizada, cualquier implementación sería una suposición.

---

## Cambios v18.0.1.8.0 — Ubicación física de moldes

### El problema que resuelve

El control en Excel mezclaba dos conceptos distintos en la misma fila: la
posición fija del molde en bodega (`RACK-1 / 3-C`) y dónde está hoy
(`LT NAL`). Por eso un molde aparecía simultáneamente en un rack propio y
en el taller de un tercero. Separados, "devolver sin memorizar" funciona
solo.

### Modelo nuevo `mrp.mold.zone`

Catálogo de zonas (RACK-0…RACK-13, TALLER ADENTRO, TALLER AFUERA,
MATERIALES, PISO MOLINO, PISO TALLER, INDEFINIDO). Agregar un rack nuevo
es crear un registro, no tocar el módulo.

Menú: **Mantenimiento → Configuración → Zonas de Almacenamiento de Moldes**.

### Campos nuevos en el molde

| Campo | Qué guarda |
|---|---|
| `mold_code` | Referencia propia del molde. NO es el código PR del producto: un producto puede tener molde nuevo y viejo, y un molde puede hacer varios productos cambiando placas. |
| `home_zone_id` / `home_position` | Su casa: posición fija. Se define una vez. |
| `current_zone_id` / `current_position` | Dónde está ahora, si está guardado. |
| `current_workcenter_id` | Si está montado en una máquina — propia o de un tercero. Los talleres externos ya existen como centros de trabajo marcados con `x_studio_ct_externo`, así que no se duplican como contactos. |
| `location_reason` | En su casa · Producción propia · Producción en tercero · Reparación |
| `location_display` | Resumen legible, almacenado, para buscar y agrupar sin abrir la ficha. |
| `is_away_from_home` | Calculado: verdadero cuando no está en su posición fija. |

### Botón "Devolver a su casa"

Copia casa → actual en un clic, y limpia el centro de trabajo. Es el
requisito operativo central: almacén no teclea rack ni posición, solo
pulsa. Falla con mensaje claro si el molde no tiene casa definida.

Visible solo cuando el molde está fuera de su casa.

### Filtros añadidos

Fuera de su casa · Sin casa definida · agrupación por Zona Casa, Zona
Actual y Motivo.

## Hallazgos del análisis de los datos (493 filas del control en Excel)

| | |
|---|---|
| Filas con código | 337 (320 códigos distintos) |
| Casillas vacías | 139 |
| Filas con "OK" en vez de código | 17 — error de digitación, se excluyen |
| **Códigos en más de una posición** | **15** — son molde nuevo y viejo del mismo producto |
| Casillas con dos códigos PR | 4 — es UN molde que hace dos productos |
| Capacidad por casilla | 144 casillas alojan 2 moldes; RACK-10 4-D llega a 8 |

Las casillas NO son exclusivas: eso descarta modelarlas como ubicaciones
de inventario, además de que el stock del producto-molde representa
amortización (vida útil), no la herramienta física.

Inconsistencias de nomenclatura detectadas: `1C`, `4C`, `4D` conviven con
`1-C`, `4-C`, `4-D`. Por eso la zona es un catálogo y no texto libre.

## Pendiente — Fases siguientes

- **Fase 2**: enlace al producto de inventario para ver la amortización
  restante en la ficha, y estado de vida útil (Activo / Amortizado /
  Dado de baja) para que el molde siga existiendo aunque llegue a cero.
- **Fase 3**: informe PDF de etiquetas con nombre, código, zona, posición
  y código de barras. Va en el módulo y no en Studio para que viaje a
  Odoo 19 y a producción sin rehacerse.

---

## Cambios v18.0.1.8.1 — Enlace al producto-molde

`product_id` (Many2one a `product.product`): el producto de categoría
`All / Materias Primas / Moldes` que representa este molde.

`mold_code` pasa a calcularse desde la **Referencia Interna** de ese
producto (ML-000403), almacenado y editable (`readonly=False`) para los
moldes que no tengan producto asociado.

### Por qué jalar del producto y no crear registros separados

El producto ya mantiene nombre, referencia y costo. Duplicarlos en el
equipo obligaría a sincronizarlos a mano para siempre. Además deja
servida la Fase 2: la amortización restante se lee del stock de ese
mismo producto, sin capturar nada nuevo.

### ATENCIÓN: los códigos PR y ML no se cruzan directamente

| Código | Qué identifica |
|---|---|
| `ML-000403` | El producto-molde |
| `PR-283-2` | El producto fabricado (preforma) |

La planilla de racks trae códigos **PR**. El puente entre ambos es la
**lista de materiales**: el producto-molde aparece como componente en la
LdM del producto PR. Por eso la asignación de rack/posición a cada molde
requiere resolver ese mapeo contra la base real antes de importar.

---

# v18.0.2.0.0 — Situación, ubicación derivada, moldes alternativos y alertas

Dependencias añadidas: `purchase`, `stock`.

## 1. Situación vs. habilitación — dos conceptos separados

| Campo | Qué es | Quién lo escribe |
|---|---|---|
| `mold_situation` | Hecho observable | Nadie: calculado |
| `is_enabled` | Decisión de mantenimiento | Manual |

`mold_situation` se calcula de: fecha de deshecho → solicitud de
mantenimiento abierta → orden de trabajo en curso → OC sin recibir →
disponible.

`is_enabled` es lo único que controla si el molde aparece en los
desplegables de LdM y orden de trabajo. **Con eso se resuelve el caso
"molde viejo y molde nuevo"**: ambos existen como equipos con su propio
ciclo y cavidades, ambos pueden estar en la lista de alternativos de la
operación, y mantenimiento inhabilita el que no debe usarse. El día que
el nuevo falle, se rehabilita el viejo y el sistema vuelve a considerarlo.

Deliberadamente NO se deriva de la fecha de compra: un molde de 2015
puede estar impecable y uno de 2024 con una cavidad rota.

## 2. Moldes alternativos por operación

`mrp.routing.workcenter.alternative_mold_ids` — el equivalente a los
centros de trabajo alternativos, pero para moldes. `all_mold_ids`
(principal + alternativos) es la lista que consultan la orden de trabajo
y, en el futuro, el planificador.

## 3. Ubicación en dos capas

**Casa**: posición fija, se define una vez.
**Actual**: derivada, con esta prioridad:

1. Override manual (gana y queda marcado con quién y cuándo)
2. Orden de trabajo en curso → su centro de trabajo
3. Solicitud de mantenimiento abierta → el taller
4. Lo último que registró almacén → o su casa

Editar los campos de ubicación marca `location_is_manual`
automáticamente; `action_return_home` lo limpia. `days_away` se cuenta
desde el hecho que sacó el molde (fecha de la solicitud o inicio de la
OT), no desde una fecha capturada a mano.

## 4. Compra por orden de compra

Un cron diario busca la OC del producto-molde y la recepción.
**La llegada se detecta por cualquier movimiento de entrada validado**,
sin depender de la cantidad: la OC puede registrarse por 1 unidad o por
las unidades de amortización, y en ambos casos la recepción es la señal
de que el molde está en planta.

## 5. Ocupación y conflictos

`_overlapping_workorders` y `get_available_molds(operation, workcenter,
date_from, date_to)`. El segundo **devuelve la lista, no elige**: es la
entrada que consumiría un planificador.

El campo `mold_conflict` es buscable mediante `_search_mold_conflict`,
que resuelve con una sola consulta en vez de calcular registro por
registro.

**Aviso, no bloqueo**: la decisión de cómo resolver un conflicto es del
planeador.

## 6. Alertas (cron diario)

| Alerta | Umbral | Parámetro de sistema |
|---|---|---|
| Fuera demasiado tiempo (reparación) | 15 días | `mrp_mold_management.alerta_dias_reparacion` |
| Fuera demasiado tiempo (maquila) | 60 días | `mrp_mold_management.alerta_dias_maquila` |
| Fuera sin solicitud de mantenimiento | inmediata | — |
| Llegada vencida | fecha prevista pasada | — |

Las alertas se crean como **actividades**, no como correo, y solo una vez
por situación: una alerta que se repite todos los días deja de leerse a
la semana.

## 7. Informe de reparaciones

`mrp.mold.repair.report` — vista SQL sobre las solicitudes de
mantenimiento de moldes. Da días por reparación, agrupables por taller.
Se apoya en la solicitud, que ya es el registro de que el molde salió: no
hace falta un histórico de ubicaciones aparte.

Validado contra PostgreSQL con datos de prueba: dos talleres con 45,5 y
12,5 días de promedio respectivamente, y detección de conflictos que
descarta correctamente las órdenes terminadas, las de otro molde y las
del mismo molde en ventana distinta.

## 8. Pantalla de planificación

Vista **nueva**, sin heredar de nada, porque el planeador no entra a la
orden de trabajo. Lista editable en línea con molde, centro de trabajo,
fechas y conflicto, filtrable por "sin molde asignado" y "con conflicto".

## Lo que NO hace, a propósito

La asignación automática cubre **solo el caso sin ambigüedad**: si la
operación tiene una única opción compatible con el centro de trabajo, se
asigna; si hay varias, se deja vacío para que la decisión sea visible.

Eso no es planificación, es un valor por defecto. Elegir optimizando
fecha de entrega, dependencias entre operaciones y carga de los centros
requiere ver todas las órdenes a la vez: pertenece a un planificador,
que es un módulo aparte.

## Riesgo controlado: vista de solicitud de mantenimiento

El xml_id del formulario de `maintenance.request` no está confirmado en
esta instancia. En vez de referenciarlo en XML estático —que ya tumbó el
ambiente dos veces en este proyecto— la vista se crea **en caliente**
desde `setup.py`, probando varios candidatos. Si no encuentra ninguno,
registra un aviso en el log y el módulo se instala igual: los campos
siguen existiendo en el modelo y solo habría que colocarlos con Studio.
