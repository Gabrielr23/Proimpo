# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def write(self, vals):
        cambia = 'user_id' in vals and vals.get('user_id')
        antes = {p.id: p.user_id.id for p in self} if cambia else {}
        res = super().write(vals)
        if cambia:
            nuevas = self.filtered(lambda p: p.user_id.id != antes.get(p.id)
                                   and p.state not in ('done', 'cancel'))
            try:
                with self.env.cr.savepoint():
                    nuevas._notify_external_molds()
            except Exception as e:  # noqa: BLE001 - nunca frena la asignación
                _logger.warning('No se pudo revisar la disponibilidad de '
                                'moldes de la orden: %s', e)
        return res

    # ------------------------------------------------------------------
    def _molds_needed(self):
        """(operación, molde) que la orden va a necesitar: el molde de la
        orden de trabajo, o el principal de la operación si aún no tiene."""
        self.ensure_one()
        pares = []
        for wo in self.workorder_ids:
            molde = wo.mold_id or wo.operation_id.mold_id
            if molde:
                pares.append((wo, molde))
        return pares

    def _notify_external_molds(self):
        """Al asignar responsable a la orden de fabricación: si algún molde
        que necesita está fuera de planta (ubicación externa, CT externo o
        taller de reparación externo), avisa al responsable de la orden y
        al responsable del molde. Nunca a ventas, y nunca bloquea."""
        Alerts = self.env['mrp.mold.alerts']
        Activity = self.env['mail.activity'].sudo()
        for prod in self:
            for wo, molde in prod._molds_needed():
                fuera, motivo, regreso = molde._external_status()
                if not fuera:
                    continue
                alternos = wo.operation_id.alternative_mold_ids.filtered(
                    lambda m: m.is_enabled and m != molde
                    and m.mold_situation not in ('baja', 'reparacion')
                    and not m._external_status()[0])
                txt_regreso = ('Regreso estimado: %s.' % regreso.strftime('%d/%m/%Y')
                               if regreso else 'Sin fecha estimada de regreso.')
                txt_alt = ('Hay moldes alternativos disponibles: %s.'
                           % ', '.join(alternos.mapped('display_name'))
                           if alternos else 'No hay molde alternativo disponible.')
                resumen = 'Molde fuera de planta: %s' % (molde.mold_code or molde.name)
                nota = ('La orden %s (operación "%s") necesita el molde %s, que '
                        'está fuera de planta: %s, hace %s días. %s %s'
                        % (prod.name, wo.name, molde.display_name, motivo,
                           molde.days_away or 0, txt_regreso, txt_alt))
                destinos = [(prod, prod.user_id)]
                resp = molde.technician_user_id or molde.owner_user_id \
                    or Alerts._configured_user('jefe')
                if resp:
                    destinos.append((molde, resp))
                for registro, user in destinos:
                    if not user:
                        continue
                    modelo = self.env['ir.model']._get(registro._name)
                    nota_reg = nota if registro is prod else (
                        'Asignada a %s. %s' % (prod.user_id.name, nota))
                    if Activity.search_count([
                            ('res_model_id', '=', modelo.id),
                            ('res_id', '=', registro.id),
                            ('user_id', '=', user.id),
                            ('summary', '=', resumen if registro is prod
                             else '%s – %s' % (resumen, prod.name))]):
                        continue
                    Activity.create({
                        'res_model_id': modelo.id,
                        'res_id': registro.id,
                        'user_id': user.id,
                        'summary': resumen if registro is prod
                        else '%s – %s' % (resumen, prod.name),
                        'note': nota_reg,
                        'date_deadline': fields.Date.context_today(self),
                    })
