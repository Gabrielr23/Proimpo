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
        _logger.info("PROIMPO aportes_mes: %s regla(s) re-aplicada(s).", tocadas)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Re-aplicar reglas PROIMPO'),
                'message': _('Se actualizaron %s regla(s): IBC, base prestaciones, FSP, SENA, ICBF.') % tocadas,
                'type': 'success',
                'sticky': False,
            },
        }
