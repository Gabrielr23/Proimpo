{
    "name": "Recurring Task Advanced",
    "version": "1.1",
    "price": 4.99,
    "currency": "USD",
    "license": "OPL-1",
    "author" : "SudoTech",
    "website": "http://www.sudotech.co.za",
    "category": "Project",
    "summary": "Project, Task, Recurring, Advanced",
    "description": """
Project - Task Recurring Advanced
=================================

Features:

    - Specify the repeating 'Assinged to' user when the recurring task is created
    - Specify the 'Stage' in which the recurring task is to be created in.
    - Specify the 'Deadline' date of the recurring task.
    - Specify the 'repeating 'name' the recurring task.

""",
    
    "depends": [
        'project',
    ],
    "data" : [
        'views/project_task.xml',
    ],
    'images': ['images/main_screenshot.png'],
    "installable": True,
}