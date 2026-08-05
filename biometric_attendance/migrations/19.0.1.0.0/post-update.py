# -*- coding: utf-8 -*-
"""
Post-update migrations for biometric_attendance 19.0.1.0.0
Odoo 18 → Odoo 19 migration script
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Post-update migration: reinitialize after upgrading to 19.0"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    print("[biometric_attendance] Starting post-update migration...")
    
    # Set default API token if not configured
    param_token = env['ir.config_parameter'].sudo().get_param('biometric_attendance.api_token')
    if not param_token:
        print("[biometric_attendance] Warning: API token not configured. Please set it in System Parameters.")
    
    cr.commit()
    print("[biometric_attendance] Post-update migration completed")
