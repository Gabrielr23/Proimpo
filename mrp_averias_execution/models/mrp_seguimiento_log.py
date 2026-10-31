# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpSeguimientoLog(models.Model):
    """Bitácora de correcciones del Seguimiento de tiempo (Fase B).

    Pedido de Laura: no restringir permisos (los supervisores no son
    administradores y ella no puede cambiarlos), sino dejar registro de
    cada corrección o borrado de un tramo ya cerrado, sin escribir en
    el chatter de la orden de fabricación (mucho ruido).

    Solo se registran cambios hechos a mano sobre tramos cerrados. Lo
    que hace el propio módulo (Registrar avance, hoja de averías,
    clasificación automática) no se registra. Nadie puede editar ni
    borrar esta bitácora desde la interfaz.
    """
    _name = 'mrp.seguimiento.log'
    _description = "Bitácora de Seguimiento de tiempo"
    _order = 'id desc'
    _rec_name = 'tramo'

    fecha = fields.Datetime(
        string="Fecha", default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one(
        'res.users', string="Usuario", default=lambda self: self.env.uid,
        readonly=True)
    accion = fields.Selection([
        ('editar', "Edición"),
        ('borrar', "Borrado"),
    ], string="Acción", required=True, readonly=True)
    workorder_id = fields.Many2one(
        'mrp.workorder', string="Orden de trabajo", ondelete='set null',
        readonly=True, index=True)
    production_id = fields.Many2one(
        'mrp.production', string="Orden de fabricación",
        related='workorder_id.production_id', store=True, readonly=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string="Centro de trabajo", readonly=True)
    linea_ref = fields.Integer(
        string="ID del tramo", readonly=True,
        help="ID de la línea de Seguimiento de tiempo (se conserva aunque "
             "la línea se haya borrado).")
    tramo = fields.Char(string="Tramo", readonly=True)
    campo = fields.Char(string="Campo", readonly=True)
    valor_anterior = fields.Char(string="Valor anterior", readonly=True)
    valor_nuevo = fields.Char(string="Valor nuevo", readonly=True)
