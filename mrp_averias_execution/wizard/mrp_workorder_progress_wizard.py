# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpWorkorderProgressWizard(models.TransientModel):
    """Wizard del botón "Registrar avance" (Fase 2).

    Cierra la línea de Seguimiento de tiempo en curso de la orden de
    trabajo -- con la cantidad y avería de ESA línea, la que se está
    cerrando, no de la nueva -- y abre una línea nueva, todo en una
    sola transacción, sin pasar por "Pausado". Confirmado con Laura:
    coexiste con el botón nativo Pausar, no lo reemplaza.
    """
    _name = 'mrp.workorder.progress.wizard'
    _description = "Registrar avance de orden de trabajo"

    workorder_id = fields.Many2one(
        'mrp.workorder', required=True,
        default=lambda self: self.env.context.get('active_id'))
    cantidad = fields.Float(
        string="Cantidad",
        help="Cantidad producida en la línea que se está cerrando "
             "(esta hora) -- no es un acumulado.")
    reporta_averia = fields.Boolean(string="¿Avería?")
    cantidad_averias = fields.Integer(string="Averías")

    @api.onchange('reporta_averia')
    def _onchange_reporta_averia(self):
        if not self.reporta_averia:
            self.cantidad_averias = 0

    def action_confirmar(self):
        self.ensure_one()
        wo = self.workorder_id

        linea_abierta = self.env['mrp.workcenter.productivity'].search([
            ('workorder_id', '=', wo.id),
            ('date_end', '=', False),
        ], limit=1, order='date_start desc')

        if not linea_abierta:
            raise UserError(_(
                "No hay una línea de Seguimiento de tiempo abierta en "
                "esta orden -- usa \"Iniciar\" primero."))

        linea_abierta.write({
            'x_studio_cantidad': self.cantidad,
            'x_studio_reporta_averia': self.reporta_averia,
            'x_studio_averias': (
                self.cantidad_averias if self.reporta_averia else 0),
        })

        # Mismo método nativo que usa "Pausar" para cerrar la línea sin
        # descuadrar la duración (confirmado con Laura: button_pending).
        wo.button_pending()
        wo.button_start()

        if self.reporta_averia:
            # En esa hora puede haber 1 o varios tipos de avería
            # (confirmado con Laura): en vez de cerrar el wizard, se
            # reusa el mismo método del botón "Tipificar" para abrir de
            # una vez la hoja de trabajo y que el operador cargue ahí
            # cada categoría con su cantidad.
            return linea_abierta.action_tipificar_averia()

        return {'type': 'ir.actions.act_window_close'}
