{
    "name": "HR Attendance Expected Times",
    "version": "1.6",
    "license": "LGPL-3",
    "depends": ["hr_attendance", "hr", "hr_holidays"],
    "author": "Proimpo SAS",
    "category": "Human Resources",
    "description": """
        Añade campos de entrada y salida esperada según el horario del empleado.
        
        Funcionalidades:
        - Calcula entrada y salida esperada basado en turnos planificados (Planning)
        - Si no hay turno, usa el horario del resource.calendar del empleado
        - Detecta automáticamente llegadas tarde y salidas tempranas
        - Maneja horarios con descansos y turnos nocturnos
        - Compatible con horarios flexibles
        - Dia no programado (fuera del calendario) se paga como extra (tope 2h)
        - Marca 'Valida con ausencia' si hay un permiso aprobado que justifica
          la llegada tarde / salida temprana (integracion con hr_holidays)
    """,
    "data": [
        "views/hr_attendance_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}