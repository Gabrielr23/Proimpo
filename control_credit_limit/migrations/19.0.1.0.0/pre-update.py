# -*- coding: utf-8 -*-
"""
Pre-update migrations for control_credit_limit 19.0.1.0.0
Odoo 18 → Odoo 19 migration script
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Pre-update migration: validate credit limit data before upgrading to 19.0"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    print("[control_credit_limit] Starting migration to 19.0.1.0.0...")
    
    # No specific cleanup needed, but we could validate partner records here
    # Ensure all partners have my_credit_limit defined
    cr.execute("""
        UPDATE res_partner 
        SET my_credit_limit = 0 
        WHERE my_credit_limit IS NULL
    """)
    
    cr.commit()
    print("[control_credit_limit] Pre-update migration completed")
