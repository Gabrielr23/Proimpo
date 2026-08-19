# -*- coding: utf-8 -*-
import logging
from odoo import models, api, _

_logger = logging.getLogger(__name__)

# Fórmulas correctas por código de regla
FORMULAS = {
    'IBC': (
        "smmlv = contract.company_id.smmlv_value\n"
        "dias = (payslip.date_to - payslip.date_from).days + 1\n"
        "base = categories.get('BASIC', 0) + categories.get('DEVSAL', 0)\n"
        "result = min(max(base, smmlv / 30.0 * min(dias, 30)), 25 * smmlv)"
    ),
    'BASE_PREST': (
        "result = categories.get('BASIC', 0) + categories.get('DEVSAL', 0) "
        "+ categories.get('AUXT', 0)"
    ),
    'FSP': "result = payslip._proimpo_fsp(IBC)",
    'APSENA': "result = payslip._proimpo_parafiscal(IBC, 0.02, 'APSENA')",
    'APICBF': "result = payslip._proimpo_parafiscal(IBC, 0.03, 'APICBF')",
}

# Fórmula de la regla de ajuste del auxilio de transporte (umbral mensual)
TRANSAJU_FORMULA = (
    "result = payslip._proimpo_transporte_ajuste("
    "categories.get('AUXT', 0), "
    "categories.get('BASIC', 0) + categories.get('DEVSAL', 0))"
)


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    @api.model
    def proimpo_reaplicar_reglas(self):
        """Deja IBC, BASE_PREST, FSP, SENA e ICBF con la fórmula correcta de la última
        versión. Se llama al instalar y con la acción 'Re-aplicar reglas PROIMPO'."""
        tocadas = 0
        for code, formula in FORMULAS.items():
            reglas = self.search([('code', '=', code)])
            for r in reglas:
                r.write({'amount_select': 'code', 'amount_python_compute': formula})
                tocadas += 1
        # --- Auxilio de transporte: crear/actualizar TRANSAJU junto a cada TRANS ---
        cat_auxt = self.env['hr.salary.rule.category'].search([('code', '=', 'AUXT')], limit=1)
        for trans in self.search([('code', '=', 'TRANS')]):
            vals = {
                'name': 'Ajuste auxilio de transporte (mes > 2 SMMLV)',
                'code': 'TRANSAJU',
                'sequence': (trans.sequence or 100) + 1,
                'struct_id': trans.struct_id.id,
                'category_id': (cat_auxt.id or trans.category_id.id),
                'condition_select': 'none',
                'amount_select': 'code',
                'amount_python_compute': TRANSAJU_FORMULA,
                'appears_on_payslip': True,
            }
            aju = self.search([('code', '=', 'TRANSAJU'),
                               ('struct_id', '=', trans.struct_id.id)], limit=1)
            if aju:
                aju.write(vals)
            else:
                self.create(vals)
            tocadas += 1

        _logger.info("PROIMPO aportes_mes: %s regla(s) re-aplicada(s).", tocadas)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Re-aplicar reglas PROIMPO'),
                'message': _('Se actualizaron %s regla(s): IBC, base prestaciones, FSP, SENA, ICBF y auxilio de transporte.') % tocadas,
                'type': 'success',
                'sticky': False,
            },
        }
