# -*- coding: utf-8 -*-
"""
Post-update migrations for generate_bank_file 19.0.1.0.0
Odoo 18 -> Odoo 19 migration script
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Post-update migration: reinitialize after upgrading to 19.0"""
    if not version:
        return

    _logger.info("[generate_bank_file] Post-update migration completada")
