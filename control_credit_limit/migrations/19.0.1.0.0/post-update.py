# -*- coding: utf-8 -*-
"""
Post-update migrations for control_credit_limit 19.0.1.0.0
Odoo 18 -> Odoo 19 migration script
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Post-update migration: reinitialize after upgrading to 19.0"""
    if not version:
        return

    # MIGRACION 19.0: se elimina el recalculo manual de
    # compute_my_credit_is_over() / compute_over_limit(). Ambos son campos
    # calculados NO almacenados (my_credit_is_over y over_limit no declaran
    # store=True), asi que llamarlos aqui no persiste nada: solo recorria
    # todos los socios con control de cupo sin efecto alguno.
    #
    # Tambien se elimina cr.commit(): Odoo confirma la transaccion al terminar
    # la actualizacion del modulo, y hacer commit a mitad de camino impide el
    # rollback si un paso posterior falla.
    _logger.info("[control_credit_limit] Post-update migration completada")
