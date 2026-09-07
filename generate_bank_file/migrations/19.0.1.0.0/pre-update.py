# -*- coding: utf-8 -*-
"""
Pre-update migrations for generate_bank_file 19.0.1.0.0
Odoo 18 -> Odoo 19 migration script
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Pre-update migration: validate bank parameter data before upgrading to 19.0"""
    if not version:
        return

    _logger.info("[generate_bank_file] Iniciando migracion a 19.0.1.0.0...")

    # Normaliza el tamano de los parametros de banco antes de la actualizacion.
    cr.execute("""
        UPDATE res_bank_parameter_value
        SET size = 1
        WHERE size IS NULL OR size <= 0
    """)

    # MIGRACION 19.0: el default de data_type era 'Numerico', un valor que no
    # pertenece a la seleccion [('N','Numerico'),('A','Alfanumerico')]. Se
    # normalizan los registros historicos que quedaron con ese valor.
    cr.execute("""
        UPDATE res_bank_parameter_value
        SET data_type = 'N'
        WHERE data_type NOT IN ('N', 'A') OR data_type IS NULL
    """)

    # MIGRACION 19.0: se elimina cr.commit(). Odoo confirma la transaccion al
    # terminar la actualizacion del modulo; hacer commit a mitad de camino
    # impide el rollback si un paso posterior falla.
    _logger.info("[generate_bank_file] Pre-update migration completada")
