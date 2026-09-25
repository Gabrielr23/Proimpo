# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class MrpAveriaReport(models.Model):
    """Reemplazo de "Averías Tipificadas" (Fase 6, primer corte).

    Laura va a eliminar el módulo viejo (mrp_averias_report), que leía
    por UNION ALL dinámico las tablas que generaba Studio para las
    plantillas de hoja de trabajo -- ya no aplica, porque desde este
    módulo ya no se usa ese mecanismo (ver quality_check.py).

    Este reporte no lee NADA de hojas viejas ni de tablas de Studio: es
    una vista SQL sobre las tablas propias de este módulo
    (mrp_averia_categoria_linea / mrp_averia_linea), cruzadas con
    control de calidad, punto de control, orden de fabricación, orden
    de trabajo, centro de trabajo, operación, producto y categoría de
    producto. Una fila por categoría de avería reportada (mismo nivel
    de detalle que la hoja).

    Mismo _name que el módulo viejo a propósito -- para que ocupe su
    lugar. Requiere que el módulo viejo esté desinstalado/eliminado
    ANTES de instalar esta versión (si no, hay choque de modelo).

    Turno: NO es x_studio_turno (ese campo no existe). Laura ya tiene
    instalado el módulo mrp_shift_resolver (v1.1.0), que agrega
    shift_name/shift_date/shift_is_planned, ya calculados y
    almacenados, directo en mrp.workcenter.productivity. Se leen tal
    cual de esa tabla -- por eso este módulo ahora depende de
    mrp_shift_resolver (ver __manifest__.py): sin esas columnas la
    vista SQL de abajo no se puede crear.
    """
    _name = 'mrp.averia.report'
    _description = "Averías Tipificadas (reporte)"
    _auto = False
    _order = 'fecha desc'

    categoria_id = fields.Many2one(
        'mrp.averia.categoria', string="Categoría de avería", readonly=True)
    cantidad = fields.Integer(string="Cantidad", readonly=True)
    descripcion = fields.Text(string="Descripción", readonly=True)

    quality_check_id = fields.Many2one(
        'quality.check', string="Control de calidad", readonly=True)
    point_id = fields.Many2one(
        'quality.point', string="Punto de control", readonly=True)
    # OJO: se asume que el campo de estado de quality.check se llama
    # "quality_state" (estándar de Odoo) -- si en esta instancia el
    # nombre real es otro, la actualización del módulo falla con un
    # error de SQL claro (columna no existe) y se corrige en una línea.
    quality_state = fields.Selection([
        ('none', "Por hacer"),
        ('pass', "Aprobado"),
        ('fail', "Fallido"),
    ], string="Estado del control", readonly=True)

    production_id = fields.Many2one(
        'mrp.production', string="Orden de fabricación", readonly=True)
    workorder_id = fields.Many2one(
        'mrp.workorder', string="Orden de trabajo", readonly=True)

    workcenter_id = fields.Many2one(
        'mrp.workcenter', string="Centro de trabajo", readonly=True)
    tipo_centro_trabajo = fields.Selection([
        ('inyectoras', "Inyectoras"),
        ('sopladoras', "Sopladoras"),
        ('impresion', "Impresión"),
        ('sellado', "Sellado"),
    ], string="Tipo de CT", readonly=True)
    operacion_id = fields.Many2one(
        'mrp.routing.workcenter', string="Operación", readonly=True)

    product_id = fields.Many2one(
        'product.product', string="Producto", readonly=True)
    product_categ_id = fields.Many2one(
        'product.category', string="Categoría de producto", readonly=True)

    fecha = fields.Datetime(
        string="Fecha (Seguimiento de tiempo)", readonly=True,
        help="Fecha/hora de inicio de la línea de Seguimiento de "
             "tiempo que originó el control de calidad -- fecha real "
             "del turno, no la fecha de creación del registro.")
    shift_name = fields.Char(string="Turno", readonly=True)
    shift_date = fields.Date(
        string="Fecha operativa del turno", readonly=True,
        help="De mrp_shift_resolver -- el día en que arrancó el turno "
             "(no el día calendario del registro, para turnos que "
             "cruzan medianoche).")
    shift_is_planned = fields.Boolean(
        string="Turno planeado", readonly=True,
        help="De mrp_shift_resolver -- False si la franja es "
             "day_period='lunch' (sin capacidad planeada, aunque la "
             "avería igual se reporta como turno extra).")
    company_id = fields.Many2one(
        'res.company', string="Compañía", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    dl.id AS id,
                    dl.categoria_id AS categoria_id,
                    dl.cantidad AS cantidad,
                    dl.descripcion AS descripcion,

                    qc.id AS quality_check_id,
                    qc.point_id AS point_id,
                    qc.quality_state AS quality_state,
                    qc.workorder_id AS workorder_id,

                    al.production_id AS production_id,
                    al.workcenter_id AS workcenter_id,
                    al.workcenter_tipo AS tipo_centro_trabajo,
                    al.operacion_id AS operacion_id,
                    al.product_id AS product_id,
                    pt.categ_id AS product_categ_id,

                    lt.date_start AS fecha,
                    lt.shift_name AS shift_name,
                    lt.shift_date AS shift_date,
                    lt.shift_is_planned AS shift_is_planned,
                    lt.company_id AS company_id

                FROM mrp_averia_categoria_linea dl
                JOIN mrp_averia_linea al ON al.id = dl.averia_linea_id
                JOIN quality_check qc ON qc.id = dl.quality_check_id
                LEFT JOIN product_product pp ON pp.id = al.product_id
                LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN mrp_workcenter_productivity lt
                    ON lt.id = qc.x_studio_linea_tiempo
            )
        """ % self._table)
