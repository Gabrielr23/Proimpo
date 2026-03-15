{
    "name": "HR Overtime Management",
    "version": "18.0.1.0.0",
    "summary": "Gestión de cupos diarios de horas extras",
    "description": "Permite registrar cupos diarios de horas extras por empleado.",
    "category": "Human Resources",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["hr"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/hr_overtime_line_views.xml"
    ],
    "installable": True,
    "application": False
}
