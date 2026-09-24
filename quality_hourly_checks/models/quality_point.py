# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)


class QualityPoint(models.Model):
    _inherit = 'quality.point'

    # ------------------------------------------------------------------
    # Campos nuevos (motor propio, no toca el mecanismo nativo de
    # "Frecuencia de control" / measure_frequency_type / measure_frequency_unit)
    # ------------------------------------------------------------------
    hourly_control_enabled = fields.Boolean(
        string='Control por horas (motor propio)',
        help=(
            "Activa el motor propio de generación de controles con "
            "periodicidad en HORAS. Es independiente del campo nativo "
            "'Frecuencia de control' (que solo admite Días, Semanas o "
            "Meses) — puede convivir con él o dejarse este último en "
            "'Bajo pedido' / 'Todos' si no se usa para este punto."
        ),
    )
    hourly_control_interval = fields.Integer(
        string='Intervalo (horas)',
        default=2,
        help=(
            'Cada cuántas horas debe generarse un nuevo control, '
            'mientras exista una Orden de Fabricación en curso para el '
            'producto vigilado por este punto de control.'
        ),
    )
    hourly_control_last_check = fields.Datetime(
        string='Último control generado (motor por horas)',
        readonly=True,
        copy=False,
        help=(
            'Se actualiza solo cada vez que el motor por horas genera '
            'un control para este punto. No editar a mano salvo para '
            'forzar que el próximo ciclo del cron vuelva a generar de '
            'inmediato (dejar vacío).'
        ),
    )

    # ------------------------------------------------------------------
    # Resolución de alcance (productos vigilados)
    # ------------------------------------------------------------------
    def _get_hourly_scope_products(self):
        """Productos a vigilar para este punto de control.

        Replica el mismo criterio que ya usa el formulario del punto de
        control: productos explícitos si los hay; si no, todos los
        productos de las categorías de producto configuradas.

        NOTA DE VERIFICACIÓN: el nombre técnico usado aquí para el campo
        de categorías es ``product_category_ids``, el más habitual en
        quality.point. Si al instalar aparece un error de campo
        desconocido, revisar en Ajustes > Técnico > Estructura de base
        de datos > Campos (modelo quality.point, filtrando por
        "categ") el nombre real y ajustarlo en este método.
        """
        self.ensure_one()
        if self.product_ids:
            return self.product_ids
        category_field = 'product_category_ids'
        if category_field in self._fields and self[category_field]:
            return self.env['product.product'].search([
                ('categ_id', 'in', self[category_field].ids),
            ])
        return self.env['product.product']

    # ------------------------------------------------------------------
    # Motor: punto de entrada de la Acción Programada
    # ------------------------------------------------------------------
    def _cron_generate_hourly_quality_checks(self):
        """Llamado por la Acción Programada (cada 15 min, ver data/ir_cron_data.xml).

        Recorre TODOS los puntos de control con el motor por horas
        activo. Un punto individual que falle no interrumpe a los
        demás (se registra en el log y se continúa).
        """
        now = fields.Datetime.now()
        points = self.search([('hourly_control_enabled', '=', True)])

        for point in points:
            try:
                point._generate_hourly_quality_check_if_due(now)
            except Exception:
                _logger.exception(
                    "Motor de control por horas: fallo generando el "
                    "control para el punto de control '%s' (id %s). Se "
                    "omite este punto y se continúa con los demás.",
                    point.title, point.id,
                )

    def _generate_hourly_quality_check_if_due(self, now):
        self.ensure_one()

        interval = self.hourly_control_interval
        if not interval or interval <= 0:
            _logger.warning(
                "Punto de control '%s' (id %s): intervalo por horas "
                "inválido (%s). Se omite hasta corregirlo.",
                self.title, self.id, interval,
            )
            return

        if self.hourly_control_last_check:
            elapsed = now - self.hourly_control_last_check
            if elapsed < timedelta(hours=interval):
                return  # todavía no toca

        products = self._get_hourly_scope_products()
        if not products:
            return

        domain = [
            ('product_id', 'in', products.ids),
            ('state', '=', 'progress'),
        ]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))

        productions = self.env['mrp.production'].search(domain)
        if not productions:
            # Nada en curso ahora mismo: no se genera control, pero
            # tampoco se actualiza hourly_control_last_check, para que
            # el siguiente ciclo del cron (15 min) vuelva a intentarlo
            # sin esperar un intervalo completo adicional.
            return

        for production in productions:
            self._create_hourly_quality_check(production)

        self.hourly_control_last_check = now

    def _create_hourly_quality_check(self, production):
        """Crea el quality.check para una orden de fabricación en curso.

        NOTA DE VERIFICACIÓN: ``production_id`` es el nombre estándar
        documentado del campo que enlaza quality.check con la orden de
        fabricación (agregado por el puente quality_mrp). Confirmar en
        Ajustes > Técnico > Estructura de base de datos > Campos
        (modelo quality.check, filtrando por "production") antes de
        activar el cron.
        """
        self.ensure_one()
        vals = {
            'point_id': self.id,
            'product_id': production.product_id.id,
            'production_id': production.id,
            'company_id': self.company_id.id,
        }
        if self.team_id:
            vals['team_id'] = self.team_id.id
        check = self.env['quality.check'].create(vals)
        _logger.info(
            "Motor de control por horas: quality.check %s creado para "
            "el punto '%s' / OF %s.",
            check.id, self.title, production.name,
        )
        return check
