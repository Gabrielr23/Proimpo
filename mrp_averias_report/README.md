# Informe de Averías Tipificadas (`mrp_averias_report`)

Modelo de solo lectura (`mrp.averia.report`) construido sobre una **vista SQL**
que une las líneas de tipificación de todas las plantillas de hoja de trabajo
de calidad. No duplica datos ni requiere automatizaciones de sincronización.

## Cadena de datos

```
mrp.workcenter.productivity      (línea de seguimiento de tiempo, averías > 0)
    ↓ x_studio_linea_tiempo
quality.check                    (MO, producto, punto de control, estado)
    ↓ x_quality_check_id
x_quality_check_worksheet_template_N          (hoja de trabajo)
    ↓ FK inverso
x_quality_check_worksheet_template_N_line_XXX (tipificaciones)  ← origen del informe
```

## Instalación

1. Copiar la carpeta `mrp_averias_report/` en el directorio de addons
   (en Odoo.sh: `/addons` del repositorio, y hacer push).
2. Ajustes → Aplicaciones → Actualizar lista de aplicaciones.
3. Buscar "Informe de Averías Tipificadas" e instalar.
4. El menú aparece en **Calidad → Averías Tipificadas**.

## Requisitos en las plantillas

Las líneas de cada hoja de trabajo deben tener estos tres campos
(nombres técnicos exactos):

| Campo | Tipo |
|---|---|
| `x_studio_turno` | selection |
| `x_studio_averias` | selection |
| `x_studio_cantidad_averias` | integer |

Las plantillas que no los tengan se omiten del informe sin provocar errores.

Los nombres de tabla generados por Studio (`_line_b6b72`, `_line_2417c`) **no
están cableados**: se descubren en tiempo de instalación consultando
`worksheet.template` e `ir.model.fields`.

## Mantenimiento

**Al crear una plantilla nueva** hay que regenerar la vista. Dos opciones:

- Actualizar el módulo (Aplicaciones → Actualizar), o
- Calidad → Averías Tipificadas → vista **Lista** → menú ⚙ Acciones →
  **Regenerar informe de averías**.

**Si se recrea una plantilla desde cero**, Studio genera nombres de tabla
nuevos. El módulo detecta las tablas desaparecidas y las omite; basta regenerar
para que vuelva a incluirlas.

**Valores de selection**: se almacenan como texto. Si se renombra una opción en
Studio, el histórico conserva el valor anterior y aparecerán ambos en el pivot.
Conviene congelar el catálogo de tipos de avería antes de acumular datos.

## Permisos

Por defecto, lectura para todos los usuarios internos (`base.group_user`). El
menú vive bajo la aplicación Calidad, así que en la práctica solo lo ven quienes
tengan acceso a ella. Para restringirlo más, editar
`security/ir.model.access.csv` y cambiar el grupo.

## Campos disponibles para agrupar y filtrar

Fecha (día/semana/mes), Turno, Tipo de Avería, Cantidad, Producto, Categoría de
Producto, Centro de Trabajo, Operación, Orden de Fabricación, Orden de Trabajo,
Punto de Control, Plantilla, Estado del Control, Compañía.

## Limitaciones conocidas

- Solo lectura. Para corregir un dato hay que abrir el control de calidad de
  origen (columna *Control de Calidad*).
- La fecha proviene de `date_start` de la línea de seguimiento de tiempo. Si el
  control no tiene `x_studio_linea_tiempo`, cae a la fecha de creación del
  control.
- No mide tiempo perdido, solo cantidad de averías y número de tipificaciones.

---

## Medidas de producción (v18.0.1.1.0)

Se añadieron `cantidad_buena` (Cantidad Producida) y `duracion`, tomadas de la
línea de seguimiento de tiempo, más las dimensiones `employee_id` (Empleado),
`loss_id` (Productividad) y `linea_tiempo_id` (Línea de Tiempo).

### Por qué la producción solo aparece en una fila

La cantidad producida pertenece a la **línea de tiempo**, no a cada
tipificación. Si una hora tiene 3 tipos de avería, repetir las 100 piezas en las
3 filas haría que el pivot reportara 300. Por eso solo se imputa a la primera
tipificación de cada hoja, marcada con `es_primera` (filtro *Filas con
producción*).

### Qué agrupación es segura para qué medida

| Agrupar por | Averías | Cantidad Producida / Duración |
|---|---|---|
| Producto, Categoría, Centro de Trabajo, Operación | correcto | correcto |
| Orden de Fabricación, Orden de Trabajo, Empleado | correcto | correcto |
| Fecha (día/semana/mes), Productividad | correcto | correcto |
| **Tipo de Avería, Turno** | correcto | **NO usar** |

Las dos últimas son atributos de la tipificación, no de la línea de tiempo: la
producción caería sobre el tipo que resultara ser el primero de la hoja. Para
analizar por tipo de avería, use solo la medida Averías.

### Campo de cantidad producida

Se detecta automáticamente entre los campos Studio numéricos de
`mrp.workcenter.productivity`. Si eligiera el equivocado, fíjelo en
Ajustes → Técnico → Parámetros del sistema:

```
Clave:  mrp_averias_report.qty_field
Valor:  <nombre técnico del campo Cantidad>
```

Después, regenerar la vista con la acción *Regenerar informe de averías*.

### Tiempo perdido por paradas

No lo cubre este módulo, y no hace falta: las paradas se registran como líneas
de seguimiento de tiempo con su motivo de pérdida (`loss_id`), y Odoo ya las
explota en **Fabricación → Informes → Rendimiento general de los equipos**.
