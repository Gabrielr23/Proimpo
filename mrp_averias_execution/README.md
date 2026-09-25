# mrp_averias_execution -- pasos manuales después de instalar/actualizar

Estos pasos NO se hacen por datos XML del módulo a propósito: dependen de
vistas de Studio ya existentes en el ambiente de PROIMPO, y un XML mal
apuntado puede tumbar la instalación para todo el ambiente de prueba
compartido. Se hacen a mano, una sola vez (sobreviven a las
actualizaciones del módulo).

## 1. Botón "Registrar avance" en la orden de trabajo

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
