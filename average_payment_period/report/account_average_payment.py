# See README.rst file on addons root folder for license details


from odoo import api, fields, models, tools


class AccountAveragePaymentReport(models.Model):
    _name = "account.average.payment.report"
    _description = "Average Payment Period"
    _auto = False
    _rec_name = "date"

    # invoice_id = fields.Many2one('account.invoice', string='Invoice', readonly=True)
    partner_id = fields.Many2one("res.partner", string="Tercero", readonly=True)
    date = fields.Date(string="Fecha")
    payment_date = fields.Date(string="Fecha de Pago", readonly=True)
    payment_days = fields.Integer(string="Dias de Pago", readonly=True, group_operator="avg")
    days_past_due = fields.Integer(string="Dias de Mora", readonly=True, group_operator="avg")
    # period_id = fields.Many2one('account.period', string="Period", readonly=True)
    journal_id = fields.Many2one("account.journal", string="Diario", readonly=True)
    move_id = fields.Many2one("account.move", string="Account Move", readonly=True)
    ref = fields.Char("Reference", readonly=True)
    # invoice_id = fields.Many2one('account.invoice',string="Invoice",readonly=True)
    account_code = fields.Char(string="Account Code", readonly=True)
    account_id = fields.Many2one("account.account", string="Account", readonly=True)
    debit = fields.Float("Debit", readonly=True)
    credit = fields.Float("Credit", readonly=True)
    balance = fields.Float("Balance", readonly=True)
    pondere = fields.Float("Promedio Ponderado Valor", readonly=True)
    #pondere_days = fields.Float("Promedio Dias Mora", readonly=True)
    amount = fields.Float("Amount", readonly=True)

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        new_fields = []
        new_fields += fields
        
        if "payment_days" in fields:
            # new_fields.remove('payment_days')
            if "pondere" not in new_fields:
                new_fields.append("pondere")
            if "amount" not in new_fields:
                new_fields.append("amount")

        #if res_days:
        #    for r in res_days:
        #        days_ponde = r["days_past_due"]
        #self.pondere_days = days_ponde
        #rint('res_days ----------------------------------',days_ponde)

        res = super().read_group(domain, new_fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        #print('res*******************************************************',res)
        
        if "payment_days" in fields:
            for line in res:
                pondere = line.get("pondere", 0.0)
                amount = line.get("amount", 0.0)
               
                if line["amount"] != 0.0 and pondere and amount:
                    line["payment_days"] = pondere / amount
                else:
                    line["payment_days"] = 0.0
                
        return res

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(
            """CREATE or REPLACE VIEW %s as (
        select l.id,
            l.partner_id,
            l.date,
            l.payment_date,
            l.payment_days,
            l.days_past_due,
            l.journal_id,
            l.move_id,
            l.debit as debit,
            l.credit as credit,
            am.name as ref,
            l.account_id as account_id,
            a.code as account_code,
            abs(coalesce(l.debit, 0.0) - coalesce(l.credit, 0.0)) * l.payment_days as pondere,
            abs(coalesce(l.debit, 0.0) - coalesce(l.credit, 0.0))  as amount,
            coalesce(l.debit, 0.0) - coalesce(l.credit, 0.0) as balance

        from    account_move_line l
                left join account_move am on (am.id=l.move_id)
                left join account_journal j on (j.id = l.journal_id)
                left join account_account a on (a.id = l.account_id)
                where am.state = 'posted' and  l.full_reconcile_id is not null and
                      j.type in ('sale', 'purchase', 'sale_refund', 'purchase_refund')
            )"""
            % (self._table)
        )
