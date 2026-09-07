# -*- coding: utf-8 -*-
"""
Pre-update migrations for control_credit_limit 19.0.1.0.0
Odoo 18 -> Odoo 19 migration script
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Pre-update migration: validate credit limit data before upgrading to 19.0"""
    if not version:
        return

    _logger.info("[control_credit_limit] Iniciando migracion a 19.0.1.0.0...")

    # my_credit_limit es required=True; se normalizan los nulos historicos.
    cr.execute("""
        UPDATE res_partner
        SET my_credit_limit = 0
        WHERE my_credit_limit IS NULL
    """)

    # MIGRACION 19.0: se elimina cr.commit() (ver nota en post-update.py).
    _logger.info("[control_credit_limit] Pre-update migration completada")
