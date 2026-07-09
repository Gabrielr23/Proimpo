# Información Exógena DIAN — módulo Odoo 18

Addon nativo para generar los formatos de información exógena (medios magnéticos)
de la DIAN a partir de la contabilidad de Odoo. Replica la lógica del módulo de
CGUNO: **formatos → conceptos → cuentas contables asociadas → Excel**.

---

## 1. Qué incluye este scaffold

| Elemento | Descripción |
|---|---|
| `exogena.formato` | Formatos DIAN (1001, 1007, 1008, 1009…) con año y versión. |
| `exogena.concepto` | Conceptos DIAN (5002, 5004…) con su tipo/columna. |
| `exogena.concepto.cuenta` | Asocia cuentas del PUC (`account.account`) a cada concepto. |
| `exogena.reporte` | Asistente que extrae de `account.move.line`, agrupa por tercero y concepto, aplica el umbral de cuantías menores y exporta el Excel. |
| Datos precargados | Formato **1001** con sus conceptos principales (sin cuentas: usted las asocia). |

Menú: **Contabilidad → Información Exógena** (Generar formato / Configuración).

## 2. Despliegue en Odoo.sh

1. Copie la carpeta `l10n_co_exogena/` al repositorio de GitHub conectado a su
   proyecto de Odoo.sh (en la raíz de addons del repo).
2. Haga *commit/push* a una rama de **desarrollo** o **staging** (no directo a
   producción). Odoo.sh detecta el addon por su `__manifest__.py`.
3. En la build de esa rama: **Aplicaciones → Actualizar lista → instalar
   "Información Exógena DIAN"**.
4. Pruebe con datos reales de la rama de staging. Cuando esté conforme, haga
   *merge* a **producción**.

## 3. Configuración (una vez por año gravable)

1. **Contabilidad → Información Exógena → Configuración → Formatos**: revise el
   Formato 1001 precargado o cree los demás (1007, 1008, 1009, 1005, 1006, 1010).
2. Abra cada **concepto** y en *Cuentas contables asociadas* agregue las cuentas
   de su PUC, indicando qué valor tomar:
   - **Débito** → pagos, costos, gastos, compras (Formato 1001).
   - **Crédito** → ingresos (1007) y retenciones practicadas (2365/2367).
   - **Saldo** → cuentas por cobrar (1008).
   - **Saldo (crédito-débito)** → cuentas por pagar (1009).
3. La configuración se conserva; el año siguiente solo duplica el formato y
   ajusta el año.

## 4. Generar

**Información Exógena → Generar formato**: elija formato y período (se autocompleta
con el año gravable), fije el umbral en UVT si aplica (12 para 1008/1009; 0 para
reportar todo) y el valor de la UVT, y pulse **Generar Excel**.

## 5. Del Excel al XML de la DIAN

El Excel que produce este módulo alimenta el **prevalidador de la DIAN**, que
genera el archivo XML final para cargar en Muisca. No sube directo a la DIAN.

## 6. Pendientes para producción (lo que su desarrollador debe afinar)

- **Layout exacto por formato.** El export actual es genérico (tercero + concepto
  + valor). Cada formato de la DIAN tiene un orden de columnas propio; ajuste el
  método `_build_xlsx` (o cree uno por formato) para que coincida con la plantilla
  del prevalidador de la versión vigente.
- **Retenciones en el 1001.** Aquí se modelan como conceptos aparte (tipo
  "Retención renta/IVA"). El 1001 real las lleva como columnas de cada fila de
  concepto; unifique según su necesidad.
- **Versión/año.** Precargado con 1001 v11 (AG2025). Valide contra la
  especificación técnica oficial: p. ej. el GMF pasó al concepto **5101** y para
  AG2026 entran 5103/5104/5105 (versión 12).
- **Tercero.** Verifique el tipo de documento (campo de la localización), el DV y
  el manejo de terceros del exterior (docs 42/43).
- **Dependencia `l10n_co`.** Si su localización usa otro nombre técnico, ajústelo
  en `__manifest__.py`.
- **Etiquetas de vista `<list>`.** Odoo 18 usa `<list>`; si su build exige la
  forma antigua, cambie `<list>` por `<tree>`.

## 7. Aviso

No soy tu asesor tributario ni de sistemas. Este es un punto de partida técnico:
valide el cumplimiento con tu contador y prueba el módulo en staging antes de
producción.
