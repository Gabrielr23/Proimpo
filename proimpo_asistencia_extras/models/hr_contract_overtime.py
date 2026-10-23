# -*- coding: utf-8 -*-
"""v2.0.3: las horas extra NATIVAS de Odoo (entrada de trabajo OVERTIME) no deben
llegar al recibo: en PROIMPO las extras se pagan por concepto (HED/HEN/HRN...) desde
los detalles de devengado. Al generar entradas de trabajo se descartan las OVERTIME,
vengan de la asistencia validada o del registro diario de horas extra.
Para volver a permitirlas: parametro del sistema proimpo_asistencia.overtime_nativo = 1."""
from odoo import models


class HrContractSinOvertimeNativo(models.AbstractModel):
    _name = 'proimpo.sin.overtime.mixin'
    _description = 'Descarta entradas OVERTIME nativas'

    def _proimpo_filtrar_overtime(self, vals_list):
        icp = self.env['ir.config_parameter'].sudo()
        if icp.get_param('proimpo_asistencia.overtime_nativo', '0') in ('1', 'True', 'true'):
            return vals_list
        ot = self.env.ref('hr_work_entry.work_entry_type_overtime', raise_if_not_found=False)
        ot_ids = set(ot.ids) if ot else set()
        ot_ids |= set(self.env['hr.work.entry.type'].sudo().search([('code', '=', 'OVERTIME')]).ids)
        if not ot_ids:
            return vals_list
        return [v for v in vals_list if v.get('work_entry_type_id') not in ot_ids]


class HrContract(models.Model):
    _inherit = ['hr.contract', 'proimpo.sin.overtime.mixin']
    _name = 'hr.contract'

    def _get_work_entries_values(self, date_start, date_stop):
        vals = super()._get_work_entries_values(date_start, date_stop)
        return self._proimpo_filtrar_overtime(vals)
