# -*- coding: utf-8 -*-
"""
Pre-update migrations for generate_bank_file 19.0.1.0.0
Odoo 18 → Odoo 19 migration script
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Pre-update migration: validate bank parameter data before upgrading to 19.0"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    print("[generate_bank_file] Starting migration to 19.0.1.0.0...")
    
    # Validate bank parameters are correctly set
    cr.execute("""
        UPDATE res_bank_parameter_value 
        SET size = 1 
        WHERE size IS NULL OR size <= 0
    """)
    
    cr.commit()
    print("[generate_bank_file] Pre-update migration completed")
