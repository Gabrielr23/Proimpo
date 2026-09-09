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
