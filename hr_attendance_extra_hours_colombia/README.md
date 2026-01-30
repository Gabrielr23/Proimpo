# Attendance Extra Hours Colombia - Odoo 18 Enterprise

## Descripción

Módulo para el cálculo automático de horas extras en Colombia según la legislación laboral colombiana.

## Características

### ✨ Funcionalidades Principales

1. **Cálculo Automático de Horas Extras**
   - Horas Extra Diurnas (6:00 AM - 9:00 PM)
   - Horas Extra Nocturnas (9:00 PM - 6:00 AM)
   - Cálculo en tiempo real basado en asistencias

2. **Visualización Completa**
   - Vista de formulario con campos de horas extras
   - Vista de árbol con totales y decoraciones
   - Vista de pivote para análisis
   - Vista de gráfico para visualización

3. **Configuración Flexible**
   - Horarios nocturnos configurables
   - Redondeo de horas personalizable
   - Configuración desde Ajustes > Asistencias

4. **Reportes y Análisis**
   - Reporte dedicado de horas extras
   - Filtros predefinidos
   - Agrupación por empleado, departamento y fecha
   - Totales automáticos

## Instalación

### Requisitos Previos

- Odoo 18 Enterprise
- Módulos dependientes instalados:
  - `hr_attendance`
  - `resource`

### Pasos de Instalación

1. **Copiar el módulo**
   ```bash
   cp -r hr_attendance_extra_hours_colombia /path/to/odoo/addons/
   ```

2. **Actualizar lista de aplicaciones**
   - Ir a Aplicaciones
   - Actualizar lista de aplicaciones (modo desarrollador)

3. **Instalar el módulo**
   - Buscar "Attendance Extra Hours Colombia"
   - Clic en "Instalar"

## Configuración

### Configuración Inicial

1. **Ir a Configuración**
   ```
   Ajustes > Asistencias > Configuración Horas Extras Colombia
   ```

2. **Parámetros Disponibles**
   - **Inicio Nocturno**: Hora de inicio del periodo nocturno (por defecto: 21.0 = 9:00 PM)
   - **Fin Nocturno**: Hora de fin del periodo nocturno (por defecto: 6.0 = 6:00 AM)
   - **Redondeo**: Minutos para redondear horas extras (por defecto: 15)

### Configuración de Empleados

1. **Asignar Calendario de Recursos**
   ```
   Empleados > [Empleado] > Pestaña Trabajo > Horario de Trabajo
   ```
   
2. **El calendario debe tener:**
   - Días laborables definidos
   - Horarios de entrada y salida por día

## Uso

### Registro de Asistencias

1. **Check-in / Check-out normal**
   - Los empleados registran entrada y salida como siempre
   - El sistema calcula automáticamente si hay horas extras

2. **Visualización de Horas Extras**
   - Las horas extras aparecen automáticamente en el formulario de asistencia
   - Se muestran separadas en diurnas y nocturnas

### Consulta de Reportes

1. **Acceder al Reporte**
   ```
   Asistencias > Horas Extras
   ```

2. **Vistas Disponibles**
   - **Pivote**: Análisis multidimensional
   - **Gráfico**: Visualización gráfica por empleado
   - **Lista**: Detalle de todas las asistencias con horas extras
   - **Formulario**: Detalle individual

3. **Filtros Útiles**
   - Con Horas Extras
   - Con Extras Diurnas
   - Con Extras Nocturnas
   - Por Empleado
   - Por Departamento
   - Por Fecha

## Ejemplo de Funcionamiento

### Caso 1: Horas Extras Diurnas

**Configuración:**
- Horario planificado: 8:00 AM - 5:00 PM
- Check-in: 8:00 AM
- Check-out: 7:30 PM

**Resultado:**
- Horas trabajadas: 11.5 horas
- Horas planificadas: 9 horas
- Horas extras diurnas: 2.5 horas
- Horas extras nocturnas: 0 horas

### Caso 2: Horas Extras Nocturnas

**Configuración:**
- Horario planificado: 2:00 PM - 10:00 PM
- Check-in: 2:00 PM
- Check-out: 11:30 PM

**Resultado:**
- Horas trabajadas: 9.5 horas
- Horas planificadas: 8 horas
- Horas extras diurnas: 1 hora (10:00 PM - 11:00 PM)
- Horas extras nocturnas: 0.5 horas (11:00 PM - 11:30 PM)

### Caso 3: Horas Extras Mixtas

**Configuración:**
- Horario planificado: 3:00 PM - 11:00 PM
- Check-in: 3:00 PM
- Check-out: 1:00 AM (día siguiente)

**Resultado:**
- Horas trabajadas: 10 horas
- Horas planificadas: 8 horas
- Horas extras diurnas: 0 horas
- Horas extras nocturnas: 2 horas (11:00 PM - 1:00 AM)

## Legislación Colombiana

### Marco Legal

Según el Código Sustantivo del Trabajo de Colombia:

- **Jornada Diurna**: 6:00 AM - 9:00 PM
- **Jornada Nocturna**: 9:00 PM - 6:00 AM
- **Recargo Nocturno**: 35% adicional sobre el valor de la hora ordinaria
- **Hora Extra Diurna**: 25% adicional sobre el valor de la hora ordinaria
- **Hora Extra Nocturna**: 75% adicional sobre el valor de la hora ordinaria

### Notas Importantes

- Este módulo solo calcula las horas, no aplica recargos económicos
- Para el cálculo de nómina, integrar con módulo de payroll
- Los recargos deben configurarse en las reglas salariales

## Campos Calculados

### En el Modelo hr.attendance

- `extra_hours_diurnal`: Horas extras en horario diurno
- `extra_hours_nocturnal`: Horas extras en horario nocturno
- `total_extra_hours`: Total de horas extras
- `planned_hours`: Horas planificadas según calendario

Todos los campos se almacenan y se recalculan automáticamente cuando cambian:
- check_in
- check_out
- employee_id
- resource_calendar_id del empleado

## Troubleshooting

### Las horas extras no se calculan

**Verificar:**
1. El empleado tiene un calendario de recursos asignado
2. El día tiene horarios definidos en el calendario
3. La asistencia tiene check-in y check-out registrados
4. El check-out es posterior al horario planificado

### Los cálculos no son correctos

**Verificar:**
1. La zona horaria del calendario de recursos
2. Los parámetros de configuración (horarios nocturnos)
3. El redondeo configurado
4. Que no haya múltiples entradas de asistencia el mismo día

## Soporte Técnico

Para reportar problemas o solicitar nuevas funcionalidades:
- Email: soporte@tuempresa.com
- Teléfono: +57 XXX XXX XXXX

## Licencia

LGPL-3

## Autor

Tu Empresa
https://www.tuempresa.com

## Versión

18.0.1.2.0

## Changelog

### 1.2.0
- Añadidas vistas completas (formulario, árbol, pivote, gráfico)
- Configuración desde ajustes de Odoo
- Reporte dedicado de horas extras
- Mejoras en cálculo con zonas horarias
- Campo de horas planificadas
- Validaciones de configuración

### 1.1.0
- Cálculo básico de horas extras
- Separación diurna/nocturna
- Redondeo configurable

### 1.0.0
- Versión inicial
