# -*- coding: utf-8 -*-
from odoo import models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # Categorias que suman al IBC como parte SALARIAL
    _PROIMPO_IBC_CAT_SAL = ('BASIC', 'DEVSAL')
    # Categoria de devengado NO salarial (para el limite del 40%).
    # El auxilio de transporte no entra aqui: vive en su propia categoria (AUXT).
    _PROIMPO_IBC_CAT_NOSAL = ('DEVNOSAL',)

    def _proimpo_cat_total(self, codes):
        """Suma de las lineas del recibo cuyas categorias esten en 'codes'."""
        self.ensure_one()
        return sum(
            line.total
            for line in self.line_ids
            if line.category_id and line.category_id.code in codes
        )

    def _proimpo_ibc_bases(self):
        """(salarial, no_salarial) de un recibo YA calculado. Se usa para leer
        los valores de la 1Q cuando se reconcilia el mes en la 2Q."""
        self.ensure_one()
        return (
            self._proimpo_cat_total(self._PROIMPO_IBC_CAT_SAL),
            self._proimpo_cat_total(self._PROIMPO_IBC_CAT_NOSAL),
        )

    def _proimpo_slip_1q(self):
        """Devuelve el recibo de la 1Q del mismo empleado y mes (dia 1 al 15).
        Vacio si no existe (p.ej. ingreso a mitad de mes)."""
        self.ensure_one()
        d = self.date_from
        if not d:
            return self.browse()
        month_start = d.replace(day=1)
        mid = d.replace(day=15)
        return self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id),
            ('date_from', '>=', month_start),
            ('date_from', '<=', mid),
        ], order='id desc', limit=1)

    def _proimpo_ibc_1393(self, sal_periodo, nosal_periodo):
        """IBC del recibo aplicando la Ley 1393/2010 (limite del 40%).

        Recibe desde la regla IBC los totales del periodo actual:
          - sal_periodo   = BASIC + DEVSAL
          - nosal_periodo = DEVNOSAL (transporte ya excluido, vive en AUXT)

        Politica PROIMPO: el ajuste del 40% se hace en la 2Q sobre el mes
        completo (1Q + 2Q). La 1Q va sin ajuste. Piso 1 SMMLV (proporcional a
        dias) y tope 25 SMMLV como en la regla original.
        """
        self.ensure_one()
        company = self.contract_id.company_id
        smmlv = company.smmlv_value or 0.0
        dias = ((self.date_to - self.date_from).days + 1) if (self.date_from and self.date_to) else 30

        sal_periodo = sal_periodo or 0.0
        nosal_periodo = nosal_periodo or 0.0

        es_2q = bool(self.date_from and self.date_from.day > 15)

        if es_2q:
            # Reconciliacion mensual: exceso del 40% sobre el mes completo,
            # aplicado en la 2Q.
            slip1 = self._proimpo_slip_1q()
            sal1, nosal1 = slip1._proimpo_ibc_bases() if slip1 else (0.0, 0.0)
            sal_mes = sal_periodo + sal1
            nosal_mes = nosal_periodo + nosal1
            total_mes = sal_mes + nosal_mes
            exceso_mes = max(nosal_mes - 0.40 * total_mes, 0.0)
            base = sal_periodo + exceso_mes
        else:
            # 1Q: sin ajuste del 40% (se hace en la 2Q)
            base = sal_periodo

        piso = (smmlv / 30.0) * min(dias, 30)
        tope = 25.0 * smmlv
        return min(max(base, piso), tope)
