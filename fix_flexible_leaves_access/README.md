# fix_flexible_leaves_access

Parche temporal para Odoo 18 Enterprise (copia migrada a 19.0; ver "Estado en Odoo 19").

## Problema

Desde el commit de Odoo `8227bbbe1410` (15-09-2026, PR odoo/odoo#261597,
opw-6142094), los usuarios **sin permisos de Ausencias** reciben un error
"Estos registros están restringidos … no tiene acceso 'leer' a Ausencias
(hr.leave)" al abrir:

- Asistencias (vista Gantt)
- Planificación (vista Gantt)

Ocurre cuando hay empleados con **horario flexible** con ausencias dentro del
rango visible.

Origen: `addons/hr_holidays/models/resource.py`,
`ResourceCalendar._get_flexible_leaves_date`, que lee `holiday_id` sin `sudo()`.

## Solución

El módulo sobrescribe `_get_flexible_leaves_date` y pasa los registros de
`resource.calendar.leaves` con `sudo()` antes de llamar al método original.
Solo se calculan fechas de indisponibilidad; no se expone información de las
ausencias al usuario.

## Instalación (Odoo.sh)

1. Copiar la carpeta `fix_flexible_leaves_access` a la raíz del repositorio.
2. Commit y push a la rama de **staging**; esperar el build.
3. Aplicaciones → quitar filtro "Aplicaciones" → buscar
   "Fix: acceso a ausencias" → **Instalar**.
4. Probar como un usuario afectado en Asistencias y Planificación.
5. Pasar a producción e instalar el módulo también allí.

## Retiro

Tras cada actualización, revisar:

```bash
cd ~/src/odoo
git log -3 --format="%ci %h %s" -- addons/hr_holidays/models/resource.py
```

Si aparece un commit posterior a `8227bbbe1410` que corrige el acceso, probar
sin el módulo en staging y, si funciona, desinstalarlo en producción.

## Estado en Odoo 19 (migración 19.0.1.0.0)

Revisión hecha contra la rama `19.0` de odoo/odoo (08-10-2026):

- `resource.calendar._get_flexible_leaves_date` **no existe** en 19.0 (ni en
  `resource` ni en `hr_holidays`). En
  `resource/models/resource_calendar.py::_unavailable_intervals_batch` los
  recursos flexibles devuelven las ausencias convertidas a UTC sin leer
  `holiday_id`, así que el AccessError original no se reproduce por esa vía.
- Consecuencia: el override de este módulo **no se ejecuta nunca** en 19.
  Instalarlo no rompe nada, pero tampoco corrige nada.

**Recomendación:** no desplegar este módulo en 19. Probar en staging con un
usuario sin permisos de Ausencias (Asistencias y Planificación en Gantt, con
empleados de horario flexible y ausencias en el rango).

**Requiere verificación manual:** en 19.0 apareció
`hr_holidays/models/resource.py::ResourceResource._format_leave`
(llamado desde `resource.resource._get_flexible_resource_valid_work_intervals`),
que lee `leave[2].filtered('holiday_id').holiday_id.request_unit_half /
request_unit_hours` **sin `sudo()`** y asumiendo un único registro. Si los
Gantt de Enterprise (planning / hr_attendance) lo llaman sin sudo, podría
reaparecer el mismo AccessError o un "Expected singleton" con ausencias
solapadas. Si ocurre en staging, el parche debe reescribirse sobre
`resource.resource._format_leave`, no sobre `_get_flexible_leaves_date`.
