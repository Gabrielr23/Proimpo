# -*- coding: utf-8 -*-
from odoo import models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _proimpo_aprendiz_struct(self):
        name = self.env['ir.config_parameter'].sudo().get_param(
            'proimpo.aprendiz_struct', 'Aprendiz Lectiva')
        return self.env['hr.payroll.structure'].search([('name', '=', name)], limit=1)

    def compute_sheet(self):
        """Antes de calcular, si el contrato está en etapa lectiva, asigna la
        estructura 'Aprendiz Lectiva' automáticamente."""
        struct = self._proimpo_aprendiz_struct()
        if struct:
            for slip in self:
                etapa = getattr(slip.contract_id, 'pila_etapa_aprendiz', False)
                if etapa == 'lectiva' and slip.struct_id != struct:
                    slip.struct_id = struct.id
        return super().compute_sheet()
