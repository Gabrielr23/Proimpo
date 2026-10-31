# -*- coding: utf-8 -*-
from odoo import models


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def _recompute_acumulado(self):
        """Recalcula x_studio_acumulado sumando x_studio_cantidad de
        todas las lineas de Seguimiento de tiempo de esta orden.

        Migrado de la Accion automatizada de Studio del instructivo
        original ("Paso 3.2: acumulado de la orden de trabajo").
        Antes el campo se llamaba x_studio_acumulado_1; Laura lo
        renombro a x_studio_acumulado -- este modulo usa el nombre
        actual.
        """
        for wo in self:
            lineas = self.env['mrp.workcenter.productivity'].search([
                ('workorder_id', '=', wo.id),
            ])
            total = sum(lineas.mapped('x_studio_cantidad'))
            wo.write({'x_studio_acumulado': total})

    # --- Fase A3: sin etiqueta nativa al abrir ------------------------
    def _prepare_timeline_vals(self, duration, date_start, date_end=False):
        """Odoo nativo decide "Velocidad reducida" AL ABRIR el tramo,
        comparando el tiempo acumulado de toda la OT (setups y paradas
        incluidos) contra la duración esperada -- no mide velocidad.
        Acá todo tramo nace como "Tiempo de productividad plena"; la
        clasificación real se hace al cerrarlo, con piezas y minutos
        (ver MrpWorkcenterProductivity._clasificar_rendimiento).

        Un tramo que se abre sin fecha de fin es un temporizador que
        arranca ahora (Iniciar, Registrar avance): queda marcado como
        registrado en vivo.
        """
        vals = super()._prepare_timeline_vals(duration, date_start, date_end)
        plena = self.env['mrp.workcenter.productivity']._perdida_plena()
        if plena:
            vals['loss_id'] = plena.id
        if not date_end:
            vals['registro_en_vivo'] = True
        return vals

    def _averia_segundos_por_pieza(self):
        """Estándar en segundos por pieza, con la misma regla que
        mrp_oee_report: ciclo efectivo del molde (actual, o teórico si
        no hay actual) ÷ cavidades; sin molde, la duración por defecto
        de la operación de la LdM (time_cycle_manual, minutos por
        unidad -- el módulo de moldes la actualiza al aplicar una
        revisión). Eficiencia del CT no aplica.

        El módulo de moldes no es dependencia (producción no lo tiene):
        sus campos se leen solo si existen.
        """
        self.ensure_one()
        if 'mold_id' in self._fields and self.mold_id:
            mold = self.mold_id
            ciclo = mold['cycle_time_effective'] if 'cycle_time_effective' in mold._fields else 0.0
            cavidades = mold['cavity_count'] if 'cavity_count' in mold._fields else 0
            if ciclo and cavidades:
                return ciclo / cavidades
        if self.operation_id and self.operation_id.time_cycle_manual:
            return self.operation_id.time_cycle_manual * 60.0
        return 0.0
