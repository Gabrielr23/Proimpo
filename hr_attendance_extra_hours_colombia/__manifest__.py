# -*- coding: utf-8 -*-
{
    "name": "Attendance Extra Hours Colombia",
    "version": "18.0.1.2.0",
    "category": "Human Resources/Attendances",
    "summary": "Horas extras diurnas y nocturnas según legislación colombiana",
    "description": """
        Módulo para el cálculo automático de horas extras en Colombia
        =================================================================
        
        Este módulo calcula automáticamente las horas extras trabajadas
        clasificándolas en:
        
        * Horas Extra Diurnas (6:00 AM - 9:00 PM)
        * Horas Extra Nocturnas (9:00 PM - 6:00 AM)
        
        El cálculo se basa en:
        - Horario planificado del empleado (calendario de recursos)
        - Horas efectivamente trabajadas (check-in / check-out)
        - Legislación laboral colombiana
        
        Características:
        - Cálculo automático en tiempo real
        - Redondeo configurable (por defecto 15 minutos)
        - Visualización en vistas de asistencia
        - Reportes personalizados
    """,
    "author": "Tu Empresa",
    "website": "https://www.tuempresa.com",
    "license": "LGPL-3",
    "depends": [
        "hr_attendance",
        "resource",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "views/hr_attendance_views.xml",
        "views/res_config_settings_views.xml",
        "views/menu_views.xml",
    ],
    "demo": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
