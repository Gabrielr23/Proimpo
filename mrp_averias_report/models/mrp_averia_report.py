# -*- coding: utf-8 -*-
import logging

from odoo import fields, models, tools

_logger = logging.getLogger(__name__)

# Campos que debe tener el modelo de LINEAS de una hoja de trabajo para que sus
# registros entren en el informe. Si una plantilla nueva no los tiene, se omite
# en silencio en lugar de romper la vista.
REQUIRED_LINE_FIELDS = (
    'x_studio_turno',
    'x_studio_averias',
    'x_studio_cantidad_averias',
)

# Parametro de sistema para forzar el campo de cantidad producida de la linea
# de seguimiento de tiempo, si la deteccion automatica elige el equivocado.
QTY_FIELD_PARAM = 'mrp_averias_report.qty_field'

# Columnas de la vista, en el orden exacto en que las produce cada SELECT del
# UNION. Cambiar este orden obliga a cambiar _build_select() y _empty_select().
VIEW_COLUMNS = (
    'id', 'date', 'turno', 'averia', 'cantidad', 'nbr',
    'es_primera', 'cantidad_buena', 'duracion',
    'check_id', 'quality_state', 'point_id', 'template_name',
    'linea_tiempo_id', 'loss_id', 'employee_id',
    'production_id', 'workorder_id', 'workcenter_id', 'operation_id',
    'product_id', 'categ_id', 'company_id',
)


class MrpAveriaReport(models.Model):
    _name = 'mrp.averia.report'
    _description = 'Averías Tipificadas'
    _auto = False
    _rec_name = 'averia'
    _order = 'date desc'

    # --- Medidas -----------------------------------------------------
    cantidad = fields.Integer(
        string='Averías', readonly=True,
        help='Piezas defectuosas de este tipo registradas en la hoja de trabajo.')
    nbr = fields.Integer(string='# Tipificaciones', readonly=True)
    cantidad_buena = fields.Float(
        string='Cantidad Producida', readonly=True, digits=(16, 2),
        help='Cantidad registrada en la línea de seguimiento de tiempo. Solo se '
             'imputa a la PRIMERA tipificación de cada línea, para que no se '
             'multiplique al sumar. Ver el filtro "Filas con producción".')
    duracion = fields.Float(
        string='Duración (min)', readonly=True, digits=(16, 2),
        help='Duración de la línea de seguimiento de tiempo. Se imputa igual '
             'que la cantidad producida: solo en la primera tipificación.')
    es_primera = fields.Boolean(
        string='Fila con producción', readonly=True,
        help='Marca la fila que lleva imputada la cantidad producida y la '
             'duración de su línea de seguimiento de tiempo.')

    # --- Dimensiones -------------------------------------------------
    date = fields.Datetime(string='Fecha', readonly=True)
    turno = fields.Char(string='Turno', readonly=True)
    averia = fields.Char(string='Tipo de Avería', readonly=True)

    check_id = fields.Many2one('quality.check', string='Control de Calidad', readonly=True)
    quality_state = fields.Selection([
        ('none', 'Pendiente'),
        ('pass', 'Aprobado'),
        ('fail', 'Fallido'),
    ], string='Estado del Control', readonly=True)
    point_id = fields.Many2one('quality.point', string='Punto de Control', readonly=True)
    template_name = fields.Char(string='Plantilla', readonly=True)

    linea_tiempo_id = fields.Many2one(
        'mrp.workcenter.productivity', string='Línea de Tiempo', readonly=True)
    loss_id = fields.Many2one(
        'mrp.workcenter.productivity.loss', string='Productividad', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', readonly=True)

    production_id = fields.Many2one('mrp.production', string='Orden de Fabricación', readonly=True)
    workorder_id = fields.Many2one('mrp.workorder', string='Orden de Trabajo', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Centro de Trabajo', readonly=True)
    operation_id = fields.Many2one('mrp.routing.workcenter', string='Operación', readonly=True)

    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    categ_id = fields.Many2one('product.category', string='Categoría de Producto', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)

    # ------------------------------------------------------------------
    # Utilidades de introspección
    # ------------------------------------------------------------------
    def _table_exists(self, table):
        self.env.cr.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
            (table,),
        )
        return bool(self.env.cr.fetchone())

    def _column_exists(self, table, column):
        self.env.cr.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s",
            (table, column),
        )
        return bool(self.env.cr.fetchone())

    def _get_qty_field(self):
        """Detecta el campo Studio de cantidad producida en la línea de tiempo.

        Se puede forzar con el parámetro de sistema
        ``mrp_averias_report.qty_field`` si la detección falla.
        """
        table = 'mrp_workcenter_productivity'

        forced = self.env['ir.config_parameter'].sudo().get_param(QTY_FIELD_PARAM)
        if forced:
            if self._column_exists(table, forced):
                return forced
            _logger.warning(
                'El parámetro %s apunta a "%s", que no existe en %s. Se ignora.',
                QTY_FIELD_PARAM, forced, table,
            )

        candidates = self.env['ir.model.fields'].sudo().search([
            ('model', '=', 'mrp.workcenter.productivity'),
            ('name', 'like', 'x_studio%'),
            ('ttype', 'in', ('integer', 'float')),
            ('store', '=', True),
        ])
        names = [f.name for f in candidates
                 if f.name != 'x_studio_averias' and self._column_exists(table, f.name)]
        if not names:
            return None

        # Preferencia por nombre antes de caer al primero disponible
        for keyword in ('cantidad', 'buena', 'produc'):
            for name in names:
                if keyword in name:
                    return name
        if len(names) > 1:
            _logger.warning(
                'Varios campos candidatos a cantidad producida (%s). Se usa "%s". '
                'Fije otro con el parámetro de sistema %s.',
                ', '.join(names), names[0], QTY_FIELD_PARAM,
            )
        return names[0]

    def _get_sources(self):
        """Descubre las tablas de líneas de tipificación de todas las plantillas.

        No se cablea ningún nombre generado por Studio: todo se deduce de
        ir_model_fields, porque los sufijos (_line_b6b72, _line_2417c) son
        aleatorios y cambian si se recrea una plantilla.
        """
        IMF = self.env['ir.model.fields'].sudo()
        sources = []

        templates = self.env['worksheet.template'].sudo().search([])
        for tmpl in templates:
            ws_model = tmpl.model_id.model
            if not ws_model:
                continue

            link = IMF.search([
                ('model', '=', ws_model),
                ('ttype', '=', 'many2one'),
                ('relation', '=', 'quality.check'),
                ('store', '=', True),
            ], limit=1)
            if not link:
                continue

            back_refs = IMF.search([
                ('ttype', '=', 'many2one'),
                ('relation', '=', ws_model),
                ('store', '=', True),
            ])
            for ref in back_refs:
                line_model = ref.model
                names = set(IMF.search([('model', '=', line_model)]).mapped('name'))
                if not set(REQUIRED_LINE_FIELDS).issubset(names):
                    continue

                line_table = line_model.replace('.', '_')
                ws_table = ws_model.replace('.', '_')
                if not (self._table_exists(line_table) and self._table_exists(ws_table)):
                    _logger.warning(
                        'Plantilla %s: tabla inexistente (%s / %s), se omite.',
                        tmpl.name, line_table, ws_table,
                    )
                    continue

                sources.append({
                    'name': tmpl.name or ws_model,
                    'line_table': line_table,
                    'ws_table': ws_table,
                    'fk': ref.name,
                    'link': link.name,
                })

        return sources

    # ------------------------------------------------------------------
    # Construcción de la vista
    # ------------------------------------------------------------------
    def _build_select(self, source, idx, flags):
        """SELECT de una plantilla.

        La cantidad producida y la duración pertenecen a la LÍNEA DE TIEMPO, no
        a cada tipificación. Si se repitieran en todas las filas, el pivot
        multiplicaría la producción por el número de averías tipificadas. Por eso
        solo se imputan a la primera tipificación de cada hoja (`es_primera`),
        que es 1:1 con la línea de tiempo.
        """
        has_wo = flags['workorder_id']
        has_linea = flags['linea_tiempo']
        qty_field = flags['qty_field']

        if has_linea:
            date_expr = 'COALESCE(mwp.date_start, qc.create_date)'
            date_join = ('LEFT JOIN mrp_workcenter_productivity mwp '
                         'ON mwp.id = qc.x_studio_linea_tiempo')
            linea_expr = 'qc.x_studio_linea_tiempo'
            qty_expr = 'COALESCE(mwp.%s, 0)' % qty_field if qty_field else '0'
            dur_expr = 'COALESCE(mwp.duration, 0)' if flags['duration'] else '0'
            loss_expr = 'mwp.loss_id' if flags['loss_id'] else 'NULL::integer'
            emp_expr = 'mwp.employee_id' if flags['employee_id'] else 'NULL::integer'
        else:
            date_expr = 'qc.create_date'
            date_join = ''
            linea_expr = 'NULL::integer'
            qty_expr = dur_expr = '0'
            loss_expr = emp_expr = 'NULL::integer'

        # Primera tipificación de la hoja, de forma determinista
        primera = ('(l.id = (SELECT MIN(l2.id) FROM {line_table} l2 '
                   'WHERE l2.{fk} = l.{fk}))').format(
            line_table=source['line_table'], fk=source['fk'])

        wo_join = 'LEFT JOIN mrp_workorder wo ON wo.id = qc.workorder_id' if has_wo else ''

        return """
            SELECT
                (l.id * 100 + {idx})            AS id,
                {date_expr}                     AS date,
                l.x_studio_turno                AS turno,
                l.x_studio_averias              AS averia,
                COALESCE(l.x_studio_cantidad_averias, 0) AS cantidad,
                1                               AS nbr,
                {primera}                       AS es_primera,
                (CASE WHEN {primera} THEN {qty_expr} ELSE 0 END)::double precision
                                                AS cantidad_buena,
                (CASE WHEN {primera} THEN {dur_expr} ELSE 0 END)::double precision
                                                AS duracion,
                qc.id                           AS check_id,
                qc.quality_state                AS quality_state,
                qc.point_id                     AS point_id,
                %s                              AS template_name,
                {linea_expr}                    AS linea_tiempo_id,
                {loss_expr}                     AS loss_id,
                {emp_expr}                      AS employee_id,
                {prod}                          AS production_id,
                {wo}                            AS workorder_id,
                {wc}                            AS workcenter_id,
                {op}                            AS operation_id,
                qc.product_id                   AS product_id,
                pt.categ_id                     AS categ_id,
                qc.company_id                   AS company_id
            FROM {line_table} l
            JOIN {ws_table} ws          ON ws.id = l.{fk}
            JOIN quality_check qc       ON qc.id = ws.{link}
            LEFT JOIN product_product pp   ON pp.id = qc.product_id
            LEFT JOIN product_template pt  ON pt.id = pp.product_tmpl_id
            {wo_join}
            {date_join}
            WHERE l.x_studio_averias IS NOT NULL
        """.format(
            idx=idx,
            date_expr=date_expr,
            primera=primera,
            qty_expr=qty_expr,
            dur_expr=dur_expr,
            linea_expr=linea_expr,
            loss_expr=loss_expr,
            emp_expr=emp_expr,
            prod='qc.production_id' if flags['production_id'] else 'NULL::integer',
            wo='qc.workorder_id' if has_wo else 'NULL::integer',
            wc='wo.workcenter_id' if has_wo else 'NULL::integer',
            op='wo.operation_id' if has_wo else 'NULL::integer',
            line_table=source['line_table'],
            ws_table=source['ws_table'],
            fk=source['fk'],
            link=source['link'],
            wo_join=wo_join,
            date_join=date_join,
        )

    def _empty_select(self):
        """Vista vacía con la misma firma de columnas.

        Permite que el modelo exista aunque todavía no haya plantillas válidas
        (p. ej. si el módulo se instala antes de configurar las hojas).
        """
        return """
            SELECT
                NULL::integer          AS id,
                NULL::timestamp        AS date,
                NULL::varchar          AS turno,
                NULL::varchar          AS averia,
                NULL::integer          AS cantidad,
                NULL::integer          AS nbr,
                NULL::boolean          AS es_primera,
                NULL::double precision AS cantidad_buena,
                NULL::double precision AS duracion,
                NULL::integer          AS check_id,
                NULL::varchar          AS quality_state,
                NULL::integer          AS point_id,
                NULL::varchar          AS template_name,
                NULL::integer          AS linea_tiempo_id,
                NULL::integer          AS loss_id,
                NULL::integer          AS employee_id,
                NULL::integer          AS production_id,
                NULL::integer          AS workorder_id,
                NULL::integer          AS workcenter_id,
                NULL::integer          AS operation_id,
                NULL::integer          AS product_id,
                NULL::integer          AS categ_id,
                NULL::integer          AS company_id
            WHERE FALSE
        """

    def init(self):
        """Regenera la vista SQL. Se ejecuta al instalar o actualizar el módulo."""
        tools.drop_view_if_exists(self.env.cr, self._table)

        sources = self._get_sources()
        if not sources:
            _logger.warning(
                'No se encontró ninguna plantilla de hoja de trabajo con los campos %s. '
                'El informe de averías queda vacío.', ', '.join(REQUIRED_LINE_FIELDS),
            )
            self.env.cr.execute(
                "CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._empty_select())
            )
            return

        qty_field = self._get_qty_field()
        flags = {
            'production_id': self._column_exists('quality_check', 'production_id'),
            'workorder_id': self._column_exists('quality_check', 'workorder_id'),
            'linea_tiempo': self._column_exists('quality_check', 'x_studio_linea_tiempo'),
            'duration': self._column_exists('mrp_workcenter_productivity', 'duration'),
            'loss_id': self._column_exists('mrp_workcenter_productivity', 'loss_id'),
            'employee_id': self._column_exists('mrp_workcenter_productivity', 'employee_id'),
            'qty_field': qty_field,
        }

        if not flags['linea_tiempo']:
            _logger.warning(
                'quality_check.x_studio_linea_tiempo no existe: sin fecha real de turno, '
                'sin cantidad producida y sin duración.'
            )
        elif not qty_field:
            _logger.warning(
                'No se detectó el campo de cantidad producida en '
                'mrp.workcenter.productivity. Fíjelo con el parámetro de sistema %s.',
                QTY_FIELD_PARAM,
            )
        else:
            _logger.info('Cantidad producida tomada de mrp_workcenter_productivity.%s',
                         qty_field)

        selects, params = [], []
        for idx, source in enumerate(sources, start=1):
            selects.append(self._build_select(source, idx, flags))
            params.append(source['name'])

        query = "CREATE OR REPLACE VIEW %s AS (%s)" % (
            self._table, ' UNION ALL '.join(selects),
        )
        self.env.cr.execute(query, params)
        _logger.info(
            'Informe de averías regenerado con %s plantilla(s): %s',
            len(sources), ', '.join(s['name'] for s in sources),
        )

    def action_rebuild_view(self):
        """Regenera la vista sin actualizar el módulo.

        Úsalo tras crear una plantilla de hoja de trabajo nueva.
        """
        self.sudo().init()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Informe de averías',
                'message': 'La vista se regeneró correctamente.',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_open_check(self):
        """Abre el control de calidad de origen desde una línea del informe."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'quality.check',
            'res_id': self.check_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
