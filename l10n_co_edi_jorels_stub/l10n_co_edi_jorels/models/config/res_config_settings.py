# -*- coding: utf-8 -*-
# Stub module - Configuración de Nómina Electrónica DIAN únicamente

import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ── Nómina Electrónica DIAN ──────────────────────────────────────────────
    edi_payroll_enable = fields.Boolean(
        related="company_id.edi_payroll_enable",
        string="Habilitar Nómina Electrónica DIAN",
        readonly=False,
    )
    edi_payroll_is_not_test = fields.Boolean(
        related="company_id.edi_payroll_is_not_test",
        string="Ambiente de producción",
        readonly=False,
    )
    edi_payroll_consolidated_enable = fields.Boolean(
        related="company_id.edi_payroll_consolidated_enable",
        string="Nómina consolidada",
        readonly=False,
    )
    edi_payroll_enable_validate_state = fields.Boolean(
        related="company_id.edi_payroll_enable_validate_state",
        string="Validar estado antes de enviar",
        readonly=False,
    )
    edi_payroll_always_validate = fields.Boolean(
        related="company_id.edi_payroll_always_validate",
        string="Siempre validar",
        readonly=False,
    )
    edi_payroll_id = fields.Char(
        related="company_id.edi_payroll_id",
        string="Software ID DIAN",
        readonly=False,
    )
    edi_payroll_pin = fields.Char(
        related="company_id.edi_payroll_pin",
        string="Software PIN DIAN",
        readonly=False,
    )
    edi_payroll_test_set_id = fields.Char(
        related="company_id.edi_payroll_test_set_id",
        string="TestSetId DIAN",
        readonly=False,
    )
    dian_certificate_p12 = fields.Binary(
        related="company_id.dian_certificate_p12",
        string="Certificado .p12 (Certicámara)",
        readonly=False,
    )
    dian_certificate_p12_filename = fields.Char(
        related="company_id.dian_certificate_p12_filename",
        readonly=False,
    )
    dian_certificate_password = fields.Char(
        related="company_id.dian_certificate_password",
        string="Contraseña certificado",
        readonly=False,
    )
