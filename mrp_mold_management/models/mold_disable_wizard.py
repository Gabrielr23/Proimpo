# -*- coding: utf-8 -*-
import base64
import csv
import io

from odoo import api, fields, models


class MrpMoldDisableWizard(models.TransientModel):
    _name = 'mrp.mold.disable.wizard'
    _description = 'Confirmar la inhabilitación de un molde'

    mold_id = fields.Many2one(
        'maintenance.equipment', string='Molde', required=True, readonly=True)
    principal_operation_ids = fields.Many2many(
        'mrp.routing.workcenter', string='LdM donde es el molde principal',
        compute='_compute_affected')
    alternative_operation_ids = fields.Many2many(
        'mrp.routing.workcenter', string='LdM donde es molde alternativo',
        compute='_compute_affected')
    workorder_ids = fields.Many2many(
        'mrp.workorder', string='Órdenes de trabajo abiertas',
        compute='_compute_affected')
    bom_count = fields.Integer(string='LdM afectadas',
                               compute='_compute_affected')
    workorder_count = fields.Integer(string='Órdenes abiertas',
                                     compute='_compute_affected')

    @api.depends('mold_id')
    def _compute_affected(self):
        for w in self:
            mold = w.mold_id.sudo()
            principal = mold.qualified_operation_ids
            alternativas = mold.alternative_operation_ids
            ordenes = mold.workorder_ids.filtered(
                lambda o: o.state not in ('done', 'cancel'))
            w.principal_operation_ids = principal
            w.alternative_operation_ids = alternativas
            w.workorder_ids = ordenes
            w.bom_count = len((principal | alternativas).mapped('bom_id'))
            w.workorder_count = len(ordenes)

    # ------------------------------------------------------------------
    def _rows(self):
        self.ensure_one()
        ldm = [['Producto', 'LdM', 'Operación', 'Centro de trabajo', 'Rol']]
        for rol, ops in (('Molde principal', self.principal_operation_ids),
                         ('Molde alternativo', self.alternative_operation_ids)):
            for op in ops:
                ldm.append([
                    op.bom_id.product_tmpl_id.display_name or '',
                    op.bom_id.display_name or '',
                    op.name or '',
                    op.workcenter_id.display_name or '',
                    rol])
        ordenes = [['Orden de fabricación', 'Producto', 'Operación',
                    'Centro de trabajo', 'Estado', 'Inicio planificado']]
        estados = dict(self.env['mrp.workorder']._fields['state']
                       ._description_selection(self.env))
        for wo in self.workorder_ids:
            ordenes.append([
                wo.production_id.name or '',
                wo.product_id.display_name or '',
                wo.name or '',
                wo.workcenter_id.display_name or '',
                estados.get(wo.state, wo.state or ''),
                fields.Datetime.to_string(wo.date_start) if wo.date_start else ''])
        return ldm, ordenes

    def action_download(self):
        """Descarga las LdM y órdenes afectadas para avisar al equipo."""
        self.ensure_one()
        ldm, ordenes = self._rows()
        codigo = (self.mold_id.mold_code or self.mold_id.name or 'molde')
        try:
            import xlsxwriter
            buf = io.BytesIO()
            wb = xlsxwriter.Workbook(buf, {'in_memory': True})
            neg = wb.add_format({'bold': True, 'bg_color': '#D9E1F2'})
            for nombre, filas in (('LdM afectadas', ldm),
                                  ('Órdenes abiertas', ordenes)):
                hoja = wb.add_worksheet(nombre)
                for i, fila in enumerate(filas):
                    for j, valor in enumerate(fila):
                        hoja.write(i, j, valor, neg if i == 0 else None)
                hoja.set_column(0, len(filas[0]) - 1, 28)
            wb.close()
            datos, nombre_archivo = buf.getvalue(), 'LdM_afectadas_%s.xlsx' % codigo
        except ImportError:
            buf = io.StringIO()
            w = csv.writer(buf)
            for fila in ldm:
                w.writerow(fila)
            w.writerow([])
            for fila in ordenes:
                w.writerow(fila)
            datos = buf.getvalue().encode('utf-8-sig')
            nombre_archivo = 'LdM_afectadas_%s.csv' % codigo
        adj = self.env['ir.attachment'].sudo().create({
            'name': nombre_archivo,
            'datas': base64.b64encode(datos),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % adj.id,
            'target': 'self',
        }

    def action_confirm(self):
        """Inhabilita el molde. No toca las LdM ni las órdenes."""
        self.ensure_one()
        self.mold_id.write({'is_enabled': False})
        self.mold_id.message_post(body=(
            'Molde inhabilitado por %s. Quedaban %s LdM y %s órdenes de '
            'trabajo abiertas que lo usan; no se modificaron.'
            % (self.env.user.name, self.bom_count, self.workorder_count)))
        return {'type': 'ir.actions.client', 'tag': 'reload'}
