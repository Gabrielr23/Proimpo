# -*- coding: utf-8 -*-
import logging
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    # ==================================================================
    # IDENTIFICACIÓN
    # ==================================================================
    is_mold = fields.Boolean(
        string='Es un Molde',
        help='Marca este equipo como molde de inyección. Habilita la pestaña '
             'de especificaciones, ubicación y situación.',
    )
    product_id = fields.Many2one(
        'product.product', string='Producto Molde',
        help='Producto de inventario que representa este molde (categoría '
             'Materias Primas / Moldes). Es la fuente de la referencia.',
    )
    mold_code = fields.Char(
        string='Referencia de Molde', index=True, copy=False,
        compute='_compute_mold_code', store=True, readonly=False,
        help='Se toma de la Referencia Interna del producto-molde '
             '(ML-000403). Editable para moldes sin producto asociado. '
             'NO es el código PR del producto fabricado.',
    )

    @api.depends('product_id', 'product_id.default_code')
    def _compute_mold_code(self):
        for eq in self:
            if eq.product_id and eq.product_id.default_code:
                eq.mold_code = eq.product_id.default_code
            elif not eq.mold_code:
                eq.mold_code = False

    # ==================================================================
    # SITUACIÓN vs HABILITACIÓN
    #
    # Dos conceptos deliberadamente separados:
    #   - SITUACIÓN: un hecho observable, calculado. Nadie lo escribe.
    #   - HABILITADO: una decisión de mantenimiento, manual. Es lo único
    #     que controla si el molde aparece en los desplegables de LdM y
    #     orden de trabajo.
    # Así el caso "molde viejo y molde nuevo" se resuelve sin inventar
    # estados: ambos existen, ambos pueden estar en la lista de
    # alternativos, y mantenimiento inhabilita el que no se debe usar.
    # ==================================================================
    is_enabled = fields.Boolean(
        string='Habilitado para Producción', default=True, tracking=True,
        help='Decisión de mantenimiento. Si se desmarca, el molde deja de '
             'aparecer para seleccionar en LdM y órdenes de trabajo, pero '
             'sigue existiendo con su historial y ubicación.',
    )
    mold_situation = fields.Selection([
        ('compra', 'Esperando compra'),
        ('disponible', 'Disponible'),
        ('produccion', 'En producción'),
        ('reparacion', 'En reparación'),
        ('baja', 'Dado de baja'),
    ], string='Situación', compute='_compute_mold_situation', store=True,
        help='Calculada a partir de hechos: orden de compra, recepción, '
             'órdenes de trabajo en curso, solicitudes de mantenimiento '
             'abiertas y fecha de deshecho. No se edita a mano.')

    @api.depends('scrap_date', 'arrival_date', 'purchase_order_id',
                 'workorder_ids.state',
                 'maintenance_ids.stage_id.done', 'maintenance_ids.archive')
    def _compute_mold_situation(self):
        for eq in self:
            if not eq.is_mold:
                eq.mold_situation = False
                continue
            if eq.scrap_date:
                eq.mold_situation = 'baja'
            elif eq._open_maintenance_requests():
                eq.mold_situation = 'reparacion'
            elif eq.workorder_ids.filtered(lambda w: w.state == 'progress'):
                eq.mold_situation = 'produccion'
            elif eq.purchase_order_id and not eq.arrival_date:
                eq.mold_situation = 'compra'
            else:
                eq.mold_situation = 'disponible'

    def _open_maintenance_requests(self):
        """Solicitudes de mantenimiento abiertas, con el mismo criterio que
        usa Odoo para `maintenance_open_count`."""
        self.ensure_one()
        return self.maintenance_ids.filtered(
            lambda r: not r.stage_id.done and not r.archive)

    # ==================================================================
    # ESPECIFICACIONES DE PRODUCCIÓN
    # ==================================================================
    cavity_count = fields.Integer(
        string='Cavidades Actuales', default=1,
        help='Cavidades activas hoy. Se actualiza tras una revisión que '
             'confirme un cambio (ver Bitácora de Revisión).')
    cycle_time_theoretical = fields.Float(
        string='Ciclo Teórico (seg)', digits=(10, 2),
        help='Ciclo de referencia original, en segundos por disparo.')
    cycle_time_current = fields.Float(
        string='Ciclo Actual (seg)', digits=(10, 2),
        help='Ciclo real vigente, en segundos por disparo. Si se deja en 0, '
             'los cálculos usan el Ciclo Teórico como respaldo.')
    cycle_time_effective = fields.Float(
        string='Ciclo Efectivo (seg)', compute='_compute_cycle_time_effective',
        digits=(10, 2), store=True,
        help='El ciclo que realmente se usa: el Actual si está informado, y '
             'si no, el Teórico. Evita que el objetivo por hora quede en '
             'cero solo porque nadie ha registrado una medición real.')

    @api.depends('cycle_time_current', 'cycle_time_theoretical')
    def _compute_cycle_time_effective(self):
        for eq in self:
            eq.cycle_time_effective = (
                eq.cycle_time_current or eq.cycle_time_theoretical)

    standard_weight_g = fields.Float(
        string='Peso Estándar Pieza (g)', digits=(10, 2))
    mold_weight_kg = fields.Float(string='Peso del Molde (kg)', digits=(10, 2))
    setup_hours = fields.Float(
        string='Setup Estimado (horas)', digits=(6, 2),
        help='Tiempo de montaje/cambio de molde. Es una restricción real '
             'para la planificación: cambiar de molde cuesta tiempo.')

    # --- Dimensiones físicas (para saber qué molde cabe dónde) ---
    width_mm = fields.Float(string='Ancho (mm)', digits=(10, 1))
    length_mm = fields.Float(string='Largo (mm)', digits=(10, 1))
    height_mm = fields.Float(string='Altura de Montaje (mm)', digits=(10, 1))

    hourly_target = fields.Float(
        string='Objetivo por Hora', compute='_compute_hourly_target',
        digits=(10, 2),
        help='Piezas esperadas por hora: 3600 / (ciclo efectivo / cavidades).')

    @api.depends('cycle_time_effective', 'cavity_count')
    def _compute_hourly_target(self):
        for eq in self:
            if eq.cycle_time_effective and eq.cavity_count:
                eq.hourly_target = 3600.0 / (
                    eq.cycle_time_effective / eq.cavity_count)
            else:
                eq.hourly_target = 0.0

    # ==================================================================
    # COMPATIBILIDAD Y USO
    # ==================================================================
    compatible_workcenter_ids = fields.Many2many(
        'mrp.workcenter',
        'maintenance_equipment_mold_workcenter_rel',
        'equipment_id', 'workcenter_id',
        string='Centros de Trabajo Compatibles',
        help='Centros donde este molde puede montarse. Sin orden de '
             'prioridad: el planeador decide.')
    qualified_operation_ids = fields.One2many(
        'mrp.routing.workcenter', 'mold_id',
        string='Operaciones con este Molde como Principal',
        help='Informativo. El vínculo se establece desde la operación.')
    alternative_operation_ids = fields.Many2many(
        'mrp.routing.workcenter',
        'mrp_routing_workcenter_alt_mold_rel',
        'mold_id', 'operation_id',
        string='Operaciones donde es Alternativo', readonly=True)

    workorder_ids = fields.One2many(
        'mrp.workorder', 'mold_id', string='Órdenes de Trabajo')

    # ==================================================================
    # COMPRA Y LLEGADA
    #
    # Campos planos, no calculados: los llena un cron diario (o se
    # escriben a mano). Un molde que llega no es un evento de minuto a
    # minuto, y así se evita que la situación dependa de búsquedas
    # costosas en cada lectura.
    # ==================================================================
    purchase_order_id = fields.Many2one(
        'purchase.order', string='Orden de Compra',
        help='OC con la que se compró este molde. Se detecta sola a partir '
             'del producto, o se asigna a mano.')
    expected_arrival_date = fields.Date(
        string='Llegada Prevista',
        help='Fecha prevista de la línea de la orden de compra.')
    arrival_date = fields.Date(
        string='Fecha de Llegada',
        help='Fecha de la recepción validada. Mientras esté vacía y haya '
             'una OC, la situación es "Esperando compra".')

    def _find_purchase_info(self):
        """Busca OC y recepción del producto-molde.

        Detecta la llegada por CUALQUIER movimiento de entrada validado,
        sin depender de la cantidad: la OC de un molde puede registrarse
        por 1 unidad o por las unidades de amortización, y en ambos casos
        la recepción es la señal de que el molde ya está en planta.
        """
        self.ensure_one()
        if not self.product_id:
            return {}

        vals = {}
        if not self.purchase_order_id:
            linea = self.env['purchase.order.line'].sudo().search([
                ('product_id', '=', self.product_id.id),
                ('state', 'in', ('purchase', 'done')),
            ], order='id desc', limit=1)
            if linea:
                vals['purchase_order_id'] = linea.order_id.id
                if 'date_planned' in linea._fields and linea.date_planned:
                    vals['expected_arrival_date'] = linea.date_planned.date()

        if not self.arrival_date:
            mov = self.env['stock.move'].sudo().search([
                ('product_id', '=', self.product_id.id),
                ('state', '=', 'done'),
                ('picking_code', '=', 'incoming'),
            ], order='date asc', limit=1)
            if mov:
                vals['arrival_date'] = mov.date.date()
        return vals

    @api.model
    def _cron_sync_mold_purchases(self):
        """Actualiza OC, llegada prevista y fecha de llegada de los moldes."""
        molds = self.sudo().search([
            ('is_mold', '=', True),
            ('product_id', '!=', False),
            ('arrival_date', '=', False),
        ])
        for mold in molds:
            vals = mold._find_purchase_info()
            if vals:
                mold.write(vals)
        _logger.info('Sincronización de compras: %s moldes revisados.',
                     len(molds))

    def action_sync_purchase(self):
        """Mismo cálculo, bajo demanda desde la ficha."""
        for mold in self:
            vals = mold._find_purchase_info()
            if vals:
                mold.write(vals)
        return True

    # ==================================================================
    # UBICACIÓN
    #
    # CASA: posición fija, se define una vez.
    # ACTUAL: derivada de hechos (OT en curso, solicitud de mantenimiento),
    #         salvo que alguien la fije a mano — ese override gana y queda
    #         marcado con quién y cuándo.
    # ==================================================================
    home_zone_id = fields.Many2one('mrp.mold.zone', string='Zona Casa')
    home_position = fields.Char(
        string='Posición Casa', help='0-A, 1-B, 3-C...')

    current_zone_id = fields.Many2one('mrp.mold.zone', string='Zona Actual')
    current_position = fields.Char(string='Posición Actual')
    current_workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Centro de Trabajo Actual')

    location_is_manual = fields.Boolean(
        string='Ubicación Fijada a Mano', readonly=True, copy=False,
        help='Alguien corrigió la ubicación manualmente, así que el cálculo '
             'automático deja de pisarla hasta que se devuelva a su casa.')
    location_manual_uid = fields.Many2one(
        'res.users', string='Fijada por', readonly=True, copy=False)
    location_manual_date = fields.Datetime(
        string='Fijada el', readonly=True, copy=False)

    location_display = fields.Char(
        string='Ubicación', compute='_compute_location', store=True,
        help='Resumen legible de dónde está el molde, para buscar, agrupar '
             'y ver en lista sin abrir la ficha.')
    is_away_from_home = fields.Boolean(
        string='Fuera de su Casa', compute='_compute_location', store=True)
    away_since = fields.Date(
        string='Fuera Desde', compute='_compute_location', store=True,
        help='Desde cuándo está fuera de su casa. Se toma del hecho que lo '
             'sacó: la fecha de la solicitud de mantenimiento o el inicio '
             'de la orden de trabajo.')
    days_away = fields.Integer(
        string='Días Fuera', compute='_compute_days_away',
        help='Días transcurridos desde que salió de su casa.')

    @api.depends('home_zone_id', 'home_position', 'current_zone_id',
                 'current_position', 'current_workcenter_id',
                 'location_is_manual', 'workorder_ids.state',
                 'workorder_ids.date_start',
                 'maintenance_ids.stage_id.done', 'maintenance_ids.archive',
                 'maintenance_ids.repair_partner_id',
                 'maintenance_ids.request_date')
    def _compute_location(self):
        for eq in self:
            etiqueta, fuera, desde = eq._resolve_location()
            eq.location_display = etiqueta
            eq.is_away_from_home = fuera
            eq.away_since = desde

    def _resolve_location(self):
        """Devuelve (etiqueta, está_fuera, desde_cuándo).

        Prioridad: override manual > OT en curso > solicitud de
        mantenimiento abierta > ubicación registrada > casa.
        """
        self.ensure_one()

        if self.location_is_manual:
            return self._manual_location_label()

        ot = self.workorder_ids.filtered(
            lambda w: w.state == 'progress' and w.workcenter_id)
        if ot:
            ot = ot.sorted('date_start')[0]
            return (ot.workcenter_id.display_name, True,
                    ot.date_start.date() if ot.date_start else None)

        sol = self._open_maintenance_requests()
        if sol:
            sol = sol.sorted('request_date')[0]
            if sol.repair_partner_id:
                etiqueta = 'Reparación: %s' % sol.repair_partner_id.display_name
            else:
                etiqueta = 'En reparación'
            return etiqueta, True, sol.request_date

        return self._manual_location_label()

    def _manual_location_label(self):
        self.ensure_one()
        if self.current_workcenter_id:
            return self.current_workcenter_id.display_name, True, self.away_since
        if self.current_zone_id:
            partes = [self.current_zone_id.name]
            if self.current_position:
                partes.append(self.current_position)
            etiqueta = ' / '.join(partes)
            en_casa = (
                self.current_zone_id == self.home_zone_id
                and (self.current_position or '') == (self.home_position or ''))
            return etiqueta, not en_casa, (None if en_casa else self.away_since)
        if self.home_zone_id:
            partes = [self.home_zone_id.name]
            if self.home_position:
                partes.append(self.home_position)
            return ' / '.join(partes), False, None
        return False, False, None

    @api.depends('away_since', 'is_away_from_home')
    def _compute_days_away(self):
        hoy = fields.Date.context_today(self)
        for eq in self:
            if eq.is_away_from_home and eq.away_since:
                eq.days_away = (hoy - eq.away_since).days
            else:
                eq.days_away = 0

    _LOCATION_FIELDS = ('current_zone_id', 'current_position',
                        'current_workcenter_id')

    def write(self, vals):
        """Marca la ubicación como manual cuando alguien la edita.

        Se excluye la escritura que hace `action_return_home`, que
        justamente limpia el override.
        """
        if (any(f in vals for f in self._LOCATION_FIELDS)
                and not self.env.context.get('mold_return_home')
                and 'location_is_manual' not in vals):
            vals = dict(vals,
                        location_is_manual=True,
                        location_manual_uid=self.env.uid,
                        location_manual_date=fields.Datetime.now())
            if not vals.get('away_since'):
                vals.setdefault('away_since', fields.Date.context_today(self))
        return super().write(vals)

    def action_return_home(self):
        """Devuelve el molde a su posición fija, sin teclear ubicaciones."""
        sin_casa = self.filtered(lambda e: not e.home_zone_id)
        if sin_casa:
            raise UserError(
                'Estos moldes no tienen Zona Casa definida, así que no hay '
                'a dónde devolverlos:\n- %s'
                % '\n- '.join(sin_casa.mapped('display_name')))

        for eq in self:
            eq.with_context(mold_return_home=True).write({
                'current_zone_id': eq.home_zone_id.id,
                'current_position': eq.home_position,
                'current_workcenter_id': False,
                'location_is_manual': False,
                'location_manual_uid': False,
                'location_manual_date': False,
                'away_since': False,
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Moldes devueltos',
                'message': 'Ubicación actualizada a la posición fija de cada molde.',
                'type': 'success',
                'sticky': False,
            },
        }

    # ==================================================================
    # DISPONIBILIDAD — la consulta que consumirá un planificador
    # ==================================================================
    @api.model
    def get_available_molds(self, operation, workcenter, date_from, date_to,
                            exclude_workorder=None):
        """Moldes candidatos libres en una ventana.

        Devuelve la lista; NO elige. Elegir con criterio de fecha de
        entrega, dependencias y carga es trabajo de un planificador, que
        es un módulo aparte: necesita ver todas las órdenes a la vez, no
        una. Este método es la entrada que ese planificador consume.
        """
        candidatos = operation.all_mold_ids.filtered(
            lambda m: m.is_enabled and m.mold_situation not in ('baja', 'reparacion'))
        if workcenter:
            candidatos = candidatos.filtered(
                lambda m: not m.compatible_workcenter_ids
                or workcenter in m.compatible_workcenter_ids)
        if not (date_from and date_to):
            return candidatos
        return candidatos.filtered(
            lambda m: not m._overlapping_workorders(
                date_from, date_to, exclude_workorder))

    def _overlapping_workorders(self, date_from, date_to, exclude=None):
        """Órdenes de trabajo que ya comprometen este molde en la ventana."""
        self.ensure_one()
        dominio = [
            ('mold_id', '=', self.id),
            ('state', 'not in', ('done', 'cancel')),
            ('date_start', '<', date_to),
            ('date_finished', '>', date_from),
        ]
        if exclude:
            dominio.append(('id', 'not in', exclude.ids))
        return self.env['mrp.workorder'].sudo().search(dominio)

    # ==================================================================
    # BITÁCORA DE REVISIÓN
    # ==================================================================
    revision_log_ids = fields.One2many(
        'mrp.mold.revision.log', 'equipment_id', string='Bitácora de Revisión')
    revision_count = fields.Integer(
        string='# Revisiones', compute='_compute_revision_count')

    @api.depends('revision_log_ids')
    def _compute_revision_count(self):
        for eq in self:
            eq.revision_count = len(eq.revision_log_ids)

    def action_view_revisions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bitácora de Revisión — %s' % self.name,
            'res_model': 'mrp.mold.revision.log',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': {'default_equipment_id': self.id},
        }

    def action_view_workorders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Órdenes de trabajo — %s' % self.name,
            'res_model': 'mrp.workorder',
            'view_mode': 'list,form',
            'domain': [('mold_id', '=', self.id)],
        }

    # ==================================================================
    # PROPAGACIÓN DEL CICLO A LA LdM
    # ==================================================================
    PUSH_PARAM = 'mrp_mold_management.push_cycle_to_routing'

    def _push_cycle_to_routing(self):
        """Escribe el ciclo vigente en las operaciones de ruta vinculadas,
        para que TODA orden creada de aquí en adelante nazca con el tiempo
        correcto, sin corregirla a mano una por una.

        Se apaga con el parámetro de sistema
        `mrp_mold_management.push_cycle_to_routing` el día que el ajuste de
        LdM pase a gestionarse por PLM.
        """
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            self.PUSH_PARAM, 'True')
        if str(enabled).lower() not in ('1', 'true'):
            return {'updated': [], 'skipped_auto': [], 'unlinked': []}

        updated, skipped_auto, unlinked = [], [], []
        for mold in self:
            if not mold.cycle_time_effective or not mold.cavity_count:
                continue
            minutos = (mold.cycle_time_effective / mold.cavity_count) / 60.0
            operaciones = mold.qualified_operation_ids
            if not operaciones:
                unlinked.append(mold.display_name)
                continue
            for op in operaciones:
                etiqueta = '%s (%s)' % (op.name, op.bom_id.display_name or '')
                if op.time_mode != 'manual':
                    skipped_auto.append(etiqueta)
                    continue
                op.sudo().write({'time_cycle_manual': minutos})
                updated.append(etiqueta)
        return {'updated': updated, 'skipped_auto': skipped_auto,
                'unlinked': unlinked}
