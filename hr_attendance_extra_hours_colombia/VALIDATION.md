# INSTRUCCIONES DE VALIDACIÓN - Módulo Horas Extras Colombia

## 1. INSTALACIÓN

### Paso 1: Copiar módulo
```bash
cp -r hr_attendance_extra_hours_colombia /path/to/odoo/addons/
```

### Paso 2: Reiniciar Odoo
```bash
./odoo-bin -c /path/to/odoo.conf --stop-after-init -d database_name -u all
./odoo-bin -c /path/to/odoo.conf
```

### Paso 3: Activar modo desarrollador
- Ir a Ajustes
- Scroll hasta el final
- Activar "Modo Desarrollador"

### Paso 4: Actualizar lista de aplicaciones
- Ir a Aplicaciones
- Clic en "Actualizar Lista de Aplicaciones"
- Confirmar

### Paso 5: Buscar e instalar
- Buscar "Attendance Extra Hours Colombia"
- Clic en "Instalar"

## 2. CONFIGURACIÓN INICIAL

### Paso 1: Configurar Calendario de Recursos
1. Ir a: **Empleados > Configuración > Horarios de Trabajo**
2. Seleccionar o crear un calendario
3. Configurar días laborables, ejemplo:
   - Lunes a Viernes: 8:00 - 12:00 y 14:00 - 18:00

### Paso 2: Asignar Calendario a Empleado
1. Ir a: **Empleados > Empleados**
2. Seleccionar un empleado
3. Pestaña "Trabajo"
4. Asignar el "Horario de Trabajo"

### Paso 3: Verificar Configuración del Módulo
1. Ir a: **Ajustes > Asistencias**
2. Buscar sección "Configuración Horas Extras Colombia"
3. Verificar valores:
   - Inicio Nocturno: 21.0 (9:00 PM)
   - Fin Nocturno: 6.0 (6:00 AM)
   - Redondeo: 15 minutos

## 3. CASOS DE PRUEBA

### CASO 1: Horas Extras Diurnas

**Configuración:**
- Empleado: Juan Pérez
- Calendario: Lunes a Viernes 8:00 - 17:00

**Prueba:**
1. Ir a: **Asistencias > Gestionar Asistencias**
2. Crear nueva asistencia:
   - Empleado: Juan Pérez
   - Check In: Hoy a las 8:00 AM
   - Check Out: Hoy a las 19:30 (7:30 PM)
3. Guardar

**Resultado Esperado:**
- Horas Trabajadas: 11.5 horas
- Horas Planificadas: 9 horas
- Horas Extra Diurnas: 2.5 horas
- Horas Extra Nocturnas: 0 horas
- Total Horas Extras: 2.5 horas

### CASO 2: Horas Extras Nocturnas

**Prueba:**
1. Crear nueva asistencia:
   - Empleado: Juan Pérez
   - Check In: Hoy a las 14:00 (2:00 PM)
   - Check Out: Hoy a las 23:30 (11:30 PM)
2. Guardar

**Resultado Esperado:**
- Horas Extra Diurnas: ~1 hora (entre las 18:00 y 21:00)
- Horas Extra Nocturnas: ~2.5 horas (entre las 21:00 y 23:30)

### CASO 3: Sin Horas Extras

**Prueba:**
1. Crear nueva asistencia:
   - Check In: Hoy a las 8:00 AM
   - Check Out: Hoy a las 17:00 (5:00 PM)
2. Guardar

**Resultado Esperado:**
- Horas Extra Diurnas: 0 horas
- Horas Extra Nocturnas: 0 horas
- Total Horas Extras: 0 horas

### CASO 4: Cruce de Medianoche

**Prueba:**
1. Crear nueva asistencia:
   - Check In: Hoy a las 20:00 (8:00 PM)
   - Check Out: Mañana a las 2:00 AM
2. Guardar

**Resultado Esperado:**
- Todas las horas extras deben ser nocturnas
- Horas Extra Nocturnas: Tiempo entre fin de jornada y 2:00 AM

## 4. VALIDACIÓN DE VISTAS

### Vista de Formulario
1. Abrir cualquier asistencia con horas extras
2. Verificar que se muestran los campos:
   - Horas Planificadas
   - Horas Extra Diurnas (azul si > 0)
   - Horas Extra Nocturnas (amarillo si > 0)
   - Total Horas Extras (verde si > 0, en negrita)

### Vista de Árbol
1. Ir a: **Asistencias > Asistencias**
2. Verificar columnas opcionales visibles:
   - Horas Planificadas
   - Horas Extra Diurnas
   - Horas Extra Nocturnas
   - Total Horas Extras
3. Verificar totales en la parte inferior

### Vista de Búsqueda
1. Clic en filtros
2. Verificar filtros disponibles:
   - Con Horas Extras
   - Con Extras Diurnas
   - Con Extras Nocturnas
3. Verificar agrupación:
   - Por Empleado
   - Por Departamento
   - Por Fecha

### Reporte de Horas Extras
1. Ir a: **Asistencias > Horas Extras**
2. Verificar que se abre con filtro pre-aplicado
3. Cambiar a vista Pivote:
   - Verificar filas por empleado
   - Verificar columnas por mes
   - Verificar medidas disponibles
4. Cambiar a vista Gráfico:
   - Verificar gráfico de barras apiladas
   - Verificar colores diferentes para diurnas/nocturnas

## 5. VALIDACIÓN DE CONFIGURACIÓN

### Cambiar Horario Nocturno
1. Ir a: **Ajustes > Asistencias**
2. Cambiar "Inicio Nocturno" a 22.0 (10:00 PM)
3. Guardar
4. Ir a: **Asistencias > Asistencias**
5. Crear asistencia de 17:00 a 22:30
6. Verificar que horas extras entre 21:00 y 22:00 son diurnas
7. Verificar que horas extras después de 22:00 son nocturnas

### Cambiar Redondeo
1. Ir a: **Ajustes > Asistencias**
2. Cambiar "Redondeo" a 30 minutos
3. Guardar
4. Crear asistencia con 1.4 horas extras
5. Verificar que se redondea a 1.5 horas

## 6. VALIDACIÓN DE SEGURIDAD

### Usuario Normal
1. Iniciar sesión como usuario sin permisos especiales
2. Ir a: **Asistencias > Asistencias**
3. Verificar que puede VER las horas extras
4. Verificar que NO puede modificar horas extras (campos calculados)

### Usuario Officer
1. Iniciar sesión como Attendance Officer
2. Verificar que puede crear/editar asistencias
3. Verificar que las horas extras se calculan automáticamente

### Usuario Manager
1. Iniciar sesión como Attendance Manager
2. Verificar acceso completo a todas las funcionalidades

## 7. VALIDACIÓN DE DATOS

### Empleado sin Calendario
1. Crear empleado sin calendario asignado
2. Crear asistencia para este empleado
3. Verificar que horas extras = 0 (no se puede calcular)

### Día sin Horario Planificado
1. Crear asistencia en sábado (si calendario solo tiene L-V)
2. Verificar que horas extras = 0

### Check-out antes de Check-in
1. Crear asistencia con check-out antes de check-in
2. Verificar que Odoo no permite guardar (validación estándar)

## 8. PRUEBAS DE RENDIMIENTO

### Carga Masiva
1. Crear 100+ asistencias con horas extras
2. Verificar que el cálculo se realiza en tiempo razonable
3. Ir a vista de árbol
4. Verificar que los totales se calculan correctamente

### Recálculo Automático
1. Abrir una asistencia existente con horas extras
2. Modificar el check-out
3. Guardar
4. Verificar que las horas extras se recalculan automáticamente

## 9. EXPORTACIÓN

### Exportar a Excel
1. Ir a: **Asistencias > Horas Extras**
2. Seleccionar varias asistencias
3. Clic en "Acción > Exportar"
4. Seleccionar campos:
   - Empleado
   - Fecha
   - Horas Extra Diurnas
   - Horas Extra Nocturnas
   - Total Horas Extras
5. Exportar y verificar archivo Excel

## 10. CHECKLIST FINAL

- [ ] Módulo instalado correctamente
- [ ] Configuración visible en Ajustes
- [ ] Campos visibles en formulario de asistencia
- [ ] Campos visibles en árbol de asistencias
- [ ] Filtros funcionando correctamente
- [ ] Reporte de Horas Extras accesible
- [ ] Vista Pivote funcional
- [ ] Vista Gráfico funcional
- [ ] Cálculo correcto de horas diurnas
- [ ] Cálculo correcto de horas nocturnas
- [ ] Redondeo aplicado correctamente
- [ ] Recálculo automático al cambiar datos
- [ ] Totales en vista árbol correctos
- [ ] Exportación a Excel funcional
- [ ] Permisos de seguridad aplicados
- [ ] Sin errores en log de Odoo

## ERRORES COMUNES Y SOLUCIONES

### Error: "No module named 'pytz'"
**Solución:**
```bash
pip3 install pytz
```

### Error: Campo no visible en vista
**Solución:**
1. Verificar modo desarrollador activado
2. Actualizar vista (Modo desarrollador > Editar Vista > Reset)
3. Limpiar caché del navegador

### Error: Horas extras siempre en 0
**Solución:**
1. Verificar que empleado tiene calendario asignado
2. Verificar que check-out > hora planificada de fin
3. Verificar que el día tiene horario en el calendario

### Error: Configuración no aparece en Ajustes
**Solución:**
1. Verificar que módulo hr_attendance está instalado
2. Actualizar módulo: `-u hr_attendance_extra_hours_colombia`
3. Verificar que archivo XML está en __manifest__.py

## CONTACTO SOPORTE

Si encuentra problemas durante la validación:
- Email: soporte@tuempresa.com
- Incluir: logs de Odoo, capturas de pantalla, descripción del error
