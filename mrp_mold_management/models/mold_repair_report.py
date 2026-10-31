# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class MrpMoldRepairReport(models.Model):
    _name = 'mrp.mold.repair.report'
    _description = 'Reparaciones de Moldes'
    _auto = False
    _order = 'request_date desc'

    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Molde', readonly=True)
    request_id = fields.Many2one(
        'maintenance.request', string='Solicitud', readonly=True)
    repair_location_type = fields.Selection([
        ('interno', 'Taller interno'),
        ('externo', 'Taller externo'),
    ], string='Dónde se Repara', readonly=True)
    repair_partner_id = fields.Many2one(
        'res.partner', string='Taller Externo', readonly=True)
    request_date = fields.Date(string='Fecha Solicitud', readonly=True)
    close_date = fields.Date(string='Fecha Cierre', readonly=True)
    is_open = fields.Boolean(string='Abierta', readonly=True)
    repair_days = fields.Integer(string='Días en Reparación', readonly=True)
    nbr = fields.Integer(string='# Reparaciones', readonly=True)

    def init(self):
        """Días de reparación por molde y por taller.

        Se apoya en la solicitud de mantenimiento, que ya es el registro de
        que el molde salió: no hace falta un histórico de ubicaciones
        aparte. De aquí sale el promedio de días por taller externo, que
        hoy no existe en ninguna parte y es material de negociación.
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    r.id                        AS id,
                    r.id                        AS request_id,
                    r.equipment_id              AS equipment_id,
                    r.repair_location_type      AS repair_location_type,
                    r.repair_partner_id         AS repair_partner_id,
                    r.request_date              AS request_date,
                    r.close_date                AS close_date,
                    (s.done IS NOT TRUE)        AS is_open,
                    GREATEST(
                        0,
                        (COALESCE(r.close_date, CURRENT_DATE) - r.request_date)
                    )                           AS repair_days,
                    1                           AS nbr
                FROM maintenance_request r
                JOIN maintenance_equipment e ON e.id = r.equipment_id
                LEFT JOIN maintenance_stage s ON s.id = r.stage_id
                WHERE e.is_mold IS TRUE
                  AND r.request_date IS NOT NULL
            )
        """ % self._table)
