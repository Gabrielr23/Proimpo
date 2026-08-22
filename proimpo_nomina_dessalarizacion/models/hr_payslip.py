# -*- coding: utf-8 -*-
from odoo import models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # Codigos de las lineas de reclasificacion (se excluyen del calculo del exceso)
    _DS_RECLAS = ('RECLAS1393SAL', 'RECLAS1393NS')

    def _ds_bases(self):
        """(salarial, no_salarial, total) de un recibo YA calculado, por categoria,
        excluyendo las lineas de reclasificacion. El total incluye el auxilio de
        transporte (AUXT), igual que tu base del 40% en el volante."""
        self.ensure_one()

        def cat(codes):
            return sum(
                l.total for l in self.line_ids
                if l.category_id and l.category_id.code in codes
                and (not l.salary_rule_id or l.salary_rule_id.code not in self._DS_RECLAS)
            )
        sal = cat(('BASIC', 'DEVSAL'))
        nosal = cat(('DEVNOSAL',))
        total = cat(('BASIC', 'DEVSAL', 'DEVNOSAL', 'AUXT'))
        return sal, nosal, total

    def _ds_slip_1q(self):
        """Recibo de la 1Q del mismo empleado y mes."""
        self.ensure_one()
        if not self.date_from:
            return self.browse()
        return self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id),
            ('date_from', '>=', self.date_from.replace(day=1)),
            ('date_from', '<=', self.date_from.replace(day=15)),
        ], order='id desc', limit=1)

    def _proimpo_exceso_1393(self, sal_2q, nosal_2q, total_2q):
        """Exceso de pagos NO salariales sobre el 40% de la remuneracion total del MES.
        Se aplica en la 2Q (reconciliando con la 1Q). Deja lo no salarial en el 40%.

        Recibe del periodo actual (desde la regla, via categories):
          sal_2q   = BASIC + DEVSAL
          nosal_2q = DEVNOSAL
          total_2q = BASIC + DEVSAL + DEVNOSAL + AUXT (incluye transporte)
        """
        self.ensure_one()
        es_2q = bool(self.date_from and self.date_from.day > 15)
        if not es_2q:
            return 0.0
        slip1 = self._ds_slip_1q()
        sal1, nosal1, total1 = slip1._ds_bases() if slip1 else (0.0, 0.0, 0.0)
        nosal_mes = (nosal_2q or 0.0) + nosal1
        total_mes = (total_2q or 0.0) + total1
        exceso = nosal_mes - 0.40 * total_mes
        return round(exceso, 2) if exceso > 0 else 0.0
