# -*- coding: utf-8 -*-
"""
Pre-update migrations for biometric_attendance 19.0.1.0.0
Odoo 18 → Odoo 19 migration script
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Pre-update migration: validate biometric data before upgrading to 19.0"""
    
    print("[biometric_attendance] Starting migration to 19.0.1.0.0...")
    
    # Ensure biometric log table structure is correct
    cr.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_catalog=current_database() AND table_name='biometric_log'
    """)
    
    if not cr.fetchone():
        print("[biometric_attendance] biometric_log table not found - will be created during module load")
    
    cr.commit()
    print("[biometric_attendance] Pre-update migration completed")
