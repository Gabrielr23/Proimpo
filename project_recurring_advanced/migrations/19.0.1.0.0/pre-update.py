# -*- coding: utf-8 -*-
"""
Pre-update migrations for project_recurring_advanced 19.0.1.0.0
Odoo 18 → Odoo 19 migration script
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Pre-update migration: cleanup before upgrading to 19.0"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Log migration start
    cr.execute("SELECT 1 FROM ir_module_module WHERE name='project_recurring_advanced'")
    if cr.fetchone():
        print("[project_recurring_advanced] Starting migration to 19.0.1.0.0...")
    
    # Cleanup: Reset any parent_id for recurring tasks (safety check)
    env['project.task'].search([
        ('parent_id', '!=', False),
        ('recurring_task', '=', True),
    ]).parent_id = False
    
    cr.commit()
    print("[project_recurring_advanced] Pre-update migration completed")
