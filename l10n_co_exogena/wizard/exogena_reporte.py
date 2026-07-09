# -*- coding: utf-8 -*-
import base64
import io

from odoo import models, fields, api, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class ExogenaReporte(models.TransientModel):
    _name = 'exogena.reporte'
    _description = 'Generador de Información Exógena DIAN'

    formato_id = fields.Many2one('exogena.formato', 'Formato', required=True)
    date_from = fields.Date('Desde', required=True)
    date_to = fields.Date('Hasta', required=True)
    company_id = fields.Many2one('res.company', 'Compañía',
                                 default=lambda self: self.env.company, required=True)
    umbral_uvt = fields.Float(
        'Umbral (UVT)', default=0.0,
        help='Saldos/pagos por tercero por debajo de este umbral (en UVT) se '
             'acumulan en el registro CUANTÍAS MENORES (222222222). '
             '0 = reportar todos los terceros. Ej.: 12 para F.1008 y F.1009.')
    uvt_valor = fields.Float('Valor UVT', default=49799.0,
                             help='Valor de la UVT del año gravable a reportar.')
    file_data = fields.Binary('Archivo', readonly=True)
    file_name = fields.Char('Nombre de archivo', readonly=True)

    @api.onchange('formato_id')
    def _onchange_formato(self):
        if self.formato_id and self.formato_id.year:
            self.date_from = fields.Date.to_date('%d-01-01' % self.formato_id.year)
            self.date_to = fields.Date.to_date('%d-12-31' % self.formato_id.year)

    # ------------------------------------------------------------------
    #  Acción principal
    # ------------------------------------------------------------------
    def action_generar(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_('La librería xlsxwriter no está disponible en el servidor.'))
        rows = self._compute_rows()
        if not rows:
            raise UserError(_('No se encontraron movimientos para el formato y período indicados.'))
        content = self._build_xlsx(rows)
        self.file_data = base64.b64encode(content)
        self.file_name = 'Formato_%s_%s.xlsx' % (self.formato_id.code, self.formato_id.year)
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file_data/%s?download=true' % (
                self._name, self.id, self.file_name),
            'target': 'self',
        }

    # ------------------------------------------------------------------
    #  Motor: extracción y agregación
    # ------------------------------------------------------------------
    def _compute_rows(self):
        """Recorre los apuntes contables validados, los agrupa por tercero y
        concepto según el mapeo de cuentas, y aplica el umbral de cuantías
        menores."""
        # 1) Mapa cuenta -> [(concepto, tipo_de_valor)]
        mapping = {}
        for concepto in self.formato_id.concepto_ids:
            for linea in concepto.cuenta_ids:
                mapping.setdefault(linea.account_id.id, []).append((concepto, linea.valor))

        account_ids = list(mapping.keys())
        if not account_ids:
            raise UserError(_(
                'El formato "%s" no tiene cuentas asociadas a sus conceptos. '
                'Configure las cuentas contables antes de generar.'
            ) % self.formato_id.display_name)

        # 2) Agregación en base de datos por tercero + cuenta
        domain = [
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('account_id', 'in', account_ids),
        ]
        groups = self.env['account.move.line']._read_group(
            domain,
            groupby=['partner_id', 'account_id'],
            aggregates=['debit:sum', 'credit:sum', 'balance:sum'],
        )

        # 3) Acumular por (tercero, concepto)
        data = {}
        for partner, account, debit, credit, balance in groups:
            for concepto, valor in mapping.get(account.id, []):
                amount = {
                    'debito': debit,
                    'credito': credit,
                    'saldo': balance,
                    'saldo_inv': -balance,
                }[valor]
                data.setdefault((partner, concepto), 0.0)
                data[(partner, concepto)] += amount

        # 4) Umbral -> consolidar cuantías menores
        umbral = self.umbral_uvt * self.uvt_valor
        rows = []
        menores = {}
        for (partner, concepto), amount in data.items():
            if self.company_id.currency_id.is_zero(amount):
                continue
            if umbral and abs(amount) < umbral:
                menores.setdefault(concepto, 0.0)
                menores[concepto] += amount
                continue
            rows.append(self._row_vals(partner, concepto, amount))

        for concepto, amount in menores.items():
            rows.append(self._row_menores(concepto, amount))

        # Orden estable: por concepto y luego por identificación
        rows.sort(key=lambda r: (r['concepto'], r['identificacion']))
        return rows

    # ------------------------------------------------------------------
    #  Construcción de filas
    # ------------------------------------------------------------------
    def _tipo_label(self, concepto):
        return dict(concepto._fields['tipo'].selection).get(concepto.tipo, '')

    def _row_vals(self, partner, concepto, amount):
        tipo_doc = ''
        if 'l10n_latam_identification_type_id' in partner._fields and \
                partner.l10n_latam_identification_type_id:
            tipo_doc = partner.l10n_latam_identification_type_id.name or ''
        return {
            'tipo_doc': tipo_doc,
            'identificacion': partner.vat or '',
            'nombre': partner.name or '',
            'direccion': partner.street or '',
            'departamento': partner.state_id.name or '',
            'municipio': partner.city or '',
            'pais': partner.country_id.name or '',
            'concepto': concepto.code,
            'tipo': self._tipo_label(concepto),
            'valor': amount,
        }

    def _row_menores(self, concepto, amount):
        company = self.company_id
        return {
            'tipo_doc': '43',
            'identificacion': '222222222',
            'nombre': 'CUANTÍAS MENORES',
            'direccion': company.street or '',
            'departamento': company.state_id.name or '',
            'municipio': company.city or '',
            'pais': company.country_id.name or 'Colombia',
            'concepto': concepto.code,
            'tipo': self._tipo_label(concepto),
            'valor': amount,
        }

    # ------------------------------------------------------------------
    #  Exportación Excel
    # ------------------------------------------------------------------
    def _build_xlsx(self, rows):
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Formato %s' % self.formato_id.code)
        bold = wb.add_format({'bold': True, 'bg_color': '#1F3864', 'font_color': '#FFFFFF'})
        money = wb.add_format({'num_format': '#,##0'})

        headers = ['Tipo Doc', 'Identificación', 'Nombre / Razón social',
                   'Dirección', 'Departamento', 'Municipio', 'País',
                   'Concepto', 'Tipo', 'Valor']
        widths = [10, 16, 40, 30, 18, 18, 14, 10, 24, 16]
        for col, (head, width) in enumerate(zip(headers, widths)):
            ws.write(0, col, head, bold)
            ws.set_column(col, col, width)
        ws.freeze_panes(1, 0)

        for i, r in enumerate(rows, start=1):
            ws.write(i, 0, r['tipo_doc'])
            ws.write(i, 1, r['identificacion'])
            ws.write(i, 2, r['nombre'])
            ws.write(i, 3, r['direccion'])
            ws.write(i, 4, r['departamento'])
            ws.write(i, 5, r['municipio'])
            ws.write(i, 6, r['pais'])
            ws.write(i, 7, r['concepto'])
            ws.write(i, 8, r['tipo'])
            ws.write_number(i, 9, round(r['valor'], 0), money)

        wb.close()
        return output.getvalue()
