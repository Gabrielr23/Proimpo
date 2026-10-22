# mrp_averias_execution -- pasos manuales después de instalar/actualizar

## 1. Botón "Registrar avance" en la orden de trabajo -- AUTOMÁTICO

Ya no es un paso manual. `data/menu_placement.xml` dispara
`mrp.averias.execution.setup.fix_registrar_avance_button()` en cada
actualización del módulo: busca en vivo la vista de `mrp.workorder` que
contiene el botón nativo "Iniciar" (`button_start`) y agrega "Registrar
avance" justo después, sin xml_id adivinado. Si por algo no aparece
(por ejemplo si ninguna vista activa de `mrp.workorder` contiene
`button_start` -- no debería pasar, pero por las dudas), el camino
manual de respaldo es:

Modo desarrollador → abrir una orden de trabajo → editar vista de
formulario → agregar, junto a Iniciar/Pausar:

```xml
<button name="%(mrp_averias_execution.action_mrp_workorder_progress_wizard)d"
        type="action" string="Registrar avance"
        class="btn-primary"
        invisible="state != 'progress'"/>
```

*(Si se edita directo en el editor visual de Studio -- no cargando un
archivo XML de datos -- el `%(module.xmlid)d` no se resuelve: hay que
usar el ID numérico de la acción `ir.actions.act_window`, visible en
Ajustes → Técnico → Acciones de la ventana.)*

Los pasos 2 y 3 de abajo SÍ siguen siendo manuales -- el botón
"Tipificar" vive dentro de una lista editable (columna de un campo
one2many), más frágil de ubicar en vivo que un botón suelto en el
header, así que por ahora no se automatizó.

## 2. Botón "Tipificar" en Seguimiento de tiempo

Ya migrado. Debe apuntar a la acción de este módulo, no a un ID de
Studio:

```xml
<button name="action_tipificar_averia" type="object" string="Tipificar"/>
```

## 3. Ocultar "Tipificar" cuando la línea no tiene avería (nuevo)

Mismo botón del paso 2, dentro de la lista editable de "Seguimiento de
tiempo" (pestaña dentro de la orden de trabajo). Agregarle la condición
de invisibilidad:

```xml
<button name="action_tipificar_averia" type="object" string="Tipificar"
        invisible="not x_studio_reporta_averia"/>
```

Con esto el botón solo aparece cuando la casilla ¿Avería? está marcada
(desde "Registrar avance" o marcada a mano en la línea). Si la línea no
reporta avería, la columna queda vacía en esa fila -- comportamiento
esperado, no un error.

## 4. Punto de control de averías (quality.point)

Ya no hace falta registrar `mrp.averia.linea` como plantilla de hoja de
trabajo (`quality_control_worksheet`) -- se intentó y quedó frágil,
ligado al Tipo del punto de control. El detalle de averías ahora se ve
directo en el formulario del control de calidad (control de calidad →
pestaña/grupo "Averías"), sin importar el Tipo configurado en el punto
de control (puede ser "Registrar cantidad" u otro). Solo se necesita
que el punto de control (`quality.point`) tenga el Producto o la
Categoría de producto correctos, para que `_crear_control_calidad()` lo
encuentre.

## 5. Menús

Se ubican solos en cada actualización del módulo (`data/menu_placement.xml`
→ `mrp.averias.execution.setup.fix_menu_placement()`), bajo Calidad:
"Registro de Averías" (todas las hojas, con su total) y, dentro de
Configuración, "Categorías de Avería".

## 6. Qué cambia en 18.0.1.6.0 (feedback de la prueba piloto)

Nada de esto requiere pasos manuales; todo se aplica al actualizar.

- **Registrar avance** cierra el tramo y abre el siguiente a la misma hora
  exacta (sin huecos ni tramos cruzados, aunque registre otro usuario).
- **Operario** (opcional): trae el del tramo abierto; si hubo cambio de
  turno (`mrp_shift_resolver`) queda vacío y el escogido va al tramo
  nuevo; el tramo que cierra conserva el operario del turno que sale.
- **Tipo de productividad**: todo tramo nace como "Tiempo de productividad
  plena". Al cerrar: rendimiento = (buenas + averías) × estándar por
  pieza ÷ minutos. ≥ umbral → plena; < umbral → "Velocidad reducida" o la
  causa de tipo Rendimiento que escojan. 0 buenas → pide motivo de parada.
  Estándar: ciclo efectivo del molde ÷ cavidades; sin molde, duración por
  defecto de la operación.
- **Umbral**: Ajustes → Técnico → Parámetros del sistema →
  `mrp_averias_execution.umbral_rendimiento` (95 por defecto).
- **Paradas dentro del tramo** (motivo + minutos) y **huecos** antes del
  tramo: se crean como líneas propias.
- **Pausar / Terminar nativos** ya no parten el tramo en "Velocidad
  reducida" por tiempo acumulado de la OT.
- **Bitácora**: Fabricación → Informes → Bitácora de Seguimiento de
  tiempo. Registra correcciones y borrados de tramos cerrados (quién,
  cuándo, antes y después). No escribe en el chatter de la OP.
- **Campos nuevos en Seguimiento de tiempo** (se pueden agregar como
  columna con Studio): "Registrado en vivo" y "Rendimiento (%)".
- **Catálogo**: "P03 Ajuste de proceso" pasa a Disponibilidad y se crea
  "P10 Proceso inestable" (Rendimiento, Inyectoras). Causas nuevas de
  velocidad (desgaste de herramienta, microparadas, etc.) se crean en
  Razones de pérdida con tipo Rendimiento y tipo de CT; aparecen solas en
  el wizard.
- Corregido: los menús "Registro de Averías" y "Averías Tipificadas" no
  se creaban al actualizar si "Categorías de Avería" ya existía.
