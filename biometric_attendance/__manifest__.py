{
    'name': 'Asistencia Biométrica',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Integración de dispositivos biométricos con asistencia de empleados',
    'description': """
        Módulo de Integración Biométrica
        =================================
        
        Características:
        ----------------
        * API REST para recibir datos de dispositivos biométricos
        * Búsqueda de empleados por cédula (identification_id)
        * Registro automático de check-in/check-out
        * Log completo de todos los eventos biométricos
        * Autenticación con Bearer token
        * Manejo de zonas horarias
        * Validaciones de negocio completas
        
        Formato de timestamp requerido:
        ------
        YYYY-MM-DD HH:MM:SS (ejemplo: 2025-11-06 05:58:53)
        
        Uso:
        ----
        1. Asegurarse de que los empleados tengan número de cédula asignado (identification_id)
        2. Configurar token de API en Ajustes > Parámetros del Sistema
        3. Configurar dispositivo biométrico para enviar datos al endpoint:
           POST /api/biometric
           Payload: [{"cedula": "1234567890", "timestamp": "2025-11-06 05:58:53", "status": "check_in"}]
           
        Documentación completa en: https://docs.tuempresa.com/biometric
    """,
    'author': 'Tu Empresa',
    'website': 'https://www.tuempresa.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
        'hr_attendance',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/biometric_log_views.xml',
        'views/hr_employee_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/icon.png'],
}