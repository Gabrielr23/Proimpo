# -*- coding: utf-8 -*-
"""
Post-update migrations for control_credit_limit 19.0.1.0.0
Odoo 18 → Odoo 19 migration script
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Post-update migration: reinitialize after upgrading to 19.0"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    print("[control_credit_limit] Starting post-update migration...")
    
    # Recompute credit limit calculations if needed
    # This ensures partner credit data is consistent
    partners = env['res.partner'].search([('check_credit_limit', '=', True)])
    for partner in partners:
        partner.compute_my_credit_is_over()
        partner.compute_over_limit()
    
    cr.commit()
    print("[control_credit_limit] Post-update migration completed")
