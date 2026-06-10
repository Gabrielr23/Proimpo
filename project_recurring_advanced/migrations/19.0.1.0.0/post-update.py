# -*- coding: utf-8 -*-
"""
Post-update migrations for project_recurring_advanced 19.0.1.0.0
Odoo 18 → Odoo 19 migration script
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Post-update migration: reinitialize views and data after upgrading to 19.0"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    print("[project_recurring_advanced] Starting post-update migration...")
    
    # Activate project_recurring_advanced view if it exists
    env.ref('project_recurring_advanced.view_project_task_form_inherit', raise_if_not_found=False).active = True
    
    cr.commit()
    print("[project_recurring_advanced] Post-update migration completed")
