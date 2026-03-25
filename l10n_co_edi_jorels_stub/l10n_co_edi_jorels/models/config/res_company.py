# -*- coding: utf-8 -*-
# Stub module - Solo campos necesarios para Nómina Electrónica DIAN
# No modifica facturación electrónica

import logging
from odoo import fields, models, api
from odoo.modules import module
from pathlib import Path
import csv

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    # ── Identificación de la empresa (para JSON DIAN nómina) ────────────────
    type_document_identification_id = fields.Many2one(
        comodel_name='l10n_co_edi_jorels.type_document_identifications',
        string="Tipo de documento de identificación",
    )
    type_organization_id = fields.Many2one(
        comodel_name='l10n_co_edi_jorels.type_organizations',
        string="Tipo de organización",
    )
    type_regime_id = fields.Many2one(
        comodel_name='l10n_co_edi_jorels.type_regimes',
        string="Tipo de régimen",
    )
    municipality_id = fields.Many2one(
        comodel_name='l10n_co_edi_jorels.municipalities',
        string="Municipio",
    )
    vat_formatted = fields.Char(
        string="NIT formateado",
        compute="_compute_vat_formatted",
        store=False,
    )

    # ── Campos EDI Nómina (usados por l10n_co_hr_payroll) ───────────────────
    api_key = fields.Char(
        string="API Key (EDIPO / servicio directo)",
        groups="base.group_system",
    )

    # Habilitación de nómina electrónica
    edi_payroll_enable = fields.Boolean(
        string="Habilitar Nómina Electrónica DIAN",
        default=False,
    )
    edi_payroll_is_not_test = fields.Boolean(
        string="Ambiente de producción (Nómina)",
        default=False,
        help="Marcar solo cuando la habilitación DIAN esté aprobada.",
    )
    edi_payroll_consolidated_enable = fields.Boolean(
        string="Habilitar nómina consolidada",
        default=False,
    )
    edi_payroll_enable_validate_state = fields.Boolean(
        string="Validar estado antes de enviar",
        default=False,
    )
    edi_payroll_always_validate = fields.Boolean(
        string="Siempre validar nómina",
        default=False,
    )

    # Credenciales software DIAN
    edi_payroll_id = fields.Char(
        string="Software ID (Nómina DIAN)",
        groups="base.group_system",
        help="ID del software registrado en el portal DIAN.",
    )
    edi_payroll_pin = fields.Char(
        string="Software PIN (Nómina DIAN)",
        groups="base.group_system",
        help="PIN del software registrado en el portal DIAN.",
    )
    edi_payroll_test_set_id = fields.Char(
        string="TestSetId (Habilitación DIAN)",
        groups="base.group_system",
        help="ID del set de pruebas asignado por DIAN para habilitación.",
    )

    # ── Campos para certificado directo (módulo l10n_co_hr_payroll_direct) ──
    dian_certificate_p12 = fields.Binary(
        string="Certificado digital (.p12)",
        groups="base.group_system",
        help="Archivo .p12 emitido por Certicámara para firma XAdES-EPES.",
    )
    dian_certificate_p12_filename = fields.Char(
        string="Nombre archivo certificado",
    )
    dian_certificate_password = fields.Char(
        string="Contraseña certificado",
        groups="base.group_system",
    )

    # ── Métodos requeridos por data/data.xml ────────────────────────────────
    def uninstall_custom_models(self, module_name):
        """
        Llamado antes de cargar datos CSV para limpiar secuencias.
        En stub: solo reinicia secuencias de las tablas de catálogos de nómina.
        """
        payroll_tables = [
            'l10n_co_edi_jorels_languages',
            'l10n_co_edi_jorels_countries',
            'l10n_co_edi_jorels_departments',
            'l10n_co_edi_jorels_municipalities',
            'l10n_co_edi_jorels_postal',
            'l10n_co_edi_jorels_postal_department',
            'l10n_co_edi_jorels_postal_municipality',
            'l10n_co_edi_jorels_payment_forms',
            'l10n_co_edi_jorels_payment_methods',
            'l10n_co_edi_jorels_payroll_periods',
            'l10n_co_edi_jorels_subtype_workers',
            'l10n_co_edi_jorels_type_contracts',
            'l10n_co_edi_jorels_type_currencies',
            'l10n_co_edi_jorels_type_document_identifications',
            'l10n_co_edi_jorels_type_environments',
            'l10n_co_edi_jorels_type_incapacities',
            'l10n_co_edi_jorels_type_payroll_notes',
            'l10n_co_edi_jorels_type_times',
            'l10n_co_edi_jorels_type_workers',
            'l10n_co_edi_jorels_type_organizations',
            'l10n_co_edi_jorels_type_regimes',
            'l10n_co_edi_jorels_type_liabilities',
        ]
        for table in payroll_tables:
            try:
                self._cr.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
                _logger.debug("Truncated table: %s", table)
            except Exception as e:
                _logger.debug("uninstall_custom_models skip %s: %s", table, e)
                self._cr.rollback()

    # ── Compute ─────────────────────────────────────────────────────────────
    @api.depends('vat', 'type_document_identification_id')
    def _compute_vat_formatted(self):
        for rec in self:
            if rec.vat:
                digits = ''.join(c for c in rec.vat if c.isdigit())
                # Para NIT (código 6) se elimina el dígito verificador
                if rec.type_document_identification_id and \
                        rec.type_document_identification_id.code == '31':
                    rec.vat_formatted = digits[:-1] if len(digits) > 1 else digits
                else:
                    rec.vat_formatted = digits
            else:
                rec.vat_formatted = ''
