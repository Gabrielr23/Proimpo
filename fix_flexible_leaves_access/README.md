# fix_flexible_leaves_access

Parche temporal para Odoo 18 Enterprise.

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
