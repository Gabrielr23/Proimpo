# Calidad - Controles Periódicos por Horas

Motor propio para generar controles de calidad (`quality.check`) con
periodicidad en **horas**, condicionados a que exista una Orden de
Fabricación (`mrp.production`) en estado **En proceso** (`progress`)
para el producto vigilado.

## Por qué existe este módulo

Odoo (18 y 19) solo admite Días, Semanas o Meses en "Frecuencia de
control" de un Punto de Control de Calidad. Además, el mecanismo nativo
"Periódicamente" no corre por reloj de fondo — se dispara desde eventos
de producción — así que ni agregando la unidad de horas se lograría un
control real cada N horas. Este módulo no toca ese mecanismo nativo: es
un motor aditivo e independiente.

## Qué agrega

- 3 campos nuevos en el modelo `quality.point` (Punto de Control de
  Calidad):
  - **Control por horas (motor propio)** — casilla para activar el
    motor en ese punto de control.
  - **Intervalo (horas)** — cada cuántas horas generar un control
    (por defecto 2).
  - **Último control generado (motor por horas)** — de solo lectura,
    la actualiza el propio motor.
- 1 Acción Programada (`ir.cron`) llamada **"Calidad: generar
  controles por horas (motor propio)"**, que corre cada 15 minutos y
  revisa todos los puntos de control con el motor activo.

No agrega vistas: los campos nuevos no aparecen solos en el formulario
del Punto de Control (evitamos heredar esa vista porque ya tiene
personalizaciones de Studio). Agrégalos tú misma desde Studio, igual
que con los campos de `mrp_mold_management`.

## Instalación

1. Sube la carpeta `quality_hourly_checks` al repositorio de módulos
   personalizados y despliega a Odoo.sh como con los demás módulos
   (`mrp_averias_report`, `mrp_mold_management`).
2. Instala el módulo desde Aplicaciones (buscar "Calidad - Controles
   Periódicos por Horas").
3. Ve a cualquier Punto de Control de Calidad y, con Studio, agrega al
   formulario los 3 campos nuevos (`hourly_control_enabled`,
   `hourly_control_interval`, `hourly_control_last_check`).

## Antes de activar el cron — verificar 2 nombres de campo

El módulo se instala con el cron **inactivo** a propósito. Antes de
activarlo, confirma en Ajustes > Técnico > Estructura de base de datos
> Campos estos dos nombres (los usé por ser los más habituales en
Odoo, pero `quality_control`/`quality_mrp` son módulos Enterprise sin
código fuente público, así que no están 100% confirmados en esta
instancia):

1. **Modelo `quality.point`**, filtrar por "categ" → confirmar que el
   campo de categorías de producto se llama `product_category_ids`.
   Si se llama distinto, ajustar el método
   `_get_hourly_scope_products()` en `models/quality_point.py`.
2. **Modelo `quality.check`**, filtrar por "production" → confirmar
   que el campo que enlaza con la Orden de Fabricación se llama
   `production_id`. Si se llama distinto, ajustar el método
   `_create_hourly_quality_check()` en `models/quality_point.py`.

Si alguno de los dos nombres está mal, el cron no se cae ni afecta a
nadie más: solo falla al crear el `quality.check` para ESE punto de
control, lo deja registrado en el log del servidor
("Motor de control por horas: fallo generando..."), y sigue
intentando con los demás puntos. Es información que se corrige y se
prueba de nuevo, sin riesgo para el resto del ambiente.

## Protocolo de prueba sugerido (ambiente compartido)

1. Configura un solo Punto de Control de prueba con el motor activo
   (por ejemplo, el mismo QCP00018 de peso, con intervalo = 2).
2. Asegúrate de tener (o crea) una Orden de Fabricación en estado "En
   proceso" para un producto de esa categoría.
3. Ve a Ajustes > Técnico > Automatización > Acciones Programadas,
   abre "Calidad: generar controles por horas (motor propio)" y usa el
   botón **"Ejecutar Manualmente"** — no esperes a que se active solo.
4. Verifica en el Punto de Control que se creó un `quality.check`
   nuevo, vinculado a la Orden de Fabricación correcta, y que
   `hourly_control_last_check` se actualizó.
5. Solo después de confirmar el paso 4, marca el cron como **Activo**.

## Diseño: qué pasa si...

- **La OF se pausa dentro de la ventana de 2h**: en el próximo ciclo
  del cron (15 min) simplemente no se encuentra ninguna
  `mrp.production` en `progress` para ese punto, no se genera control,
  y **no se actualiza** `hourly_control_last_check` — así que en
  cuanto la OF se reanude, el próximo ciclo del cron sí generará el
  control (no hay que esperar un intervalo completo adicional).
- **Hay 2 OF en curso simultáneas para el mismo producto/punto de
  control**: se genera un `quality.check` por cada una.
- **Se agrega un nuevo control por horas para otro producto
  semi-terminado**: solo se crea el Punto de Control nuevo (como
  siempre) y se marca la casilla + intervalo. El cron ya existente lo
  recoge automáticamente, sin tocar código.
