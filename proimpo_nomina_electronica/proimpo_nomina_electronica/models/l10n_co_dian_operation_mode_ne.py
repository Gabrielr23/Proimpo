# -*- coding: utf-8 -*-
"""Extiende el modo de operación DIAN nativo para soportar Nómina Electrónica.

Así los 3 datos de la habilitación (Software ID, PIN y TestSetID) se registran en
la MISMA pantalla nativa de Odoo (Ajustes > Contabilidad > Localización colombiana >
Modos de operación DIAN), reutilizando el modelo `l10n_co_dian.operation_mode` y su
flujo de firma/envío, sin duplicar configuración.
"""
from odoo import models, fields


class L10nCoDianOperationMode(models.Model):
    _inherit = 'l10n_co_dian.operation_mode'

    # Añade la opción "Nómina Electrónica" al selector de tipo de documento del modo.
    dian_software_operation_mode = fields.Selection(
        selection_add=[('payroll', "DIAN: Nómina Electrónica")],
        ondelete={'payroll': 'cascade'},
    )
