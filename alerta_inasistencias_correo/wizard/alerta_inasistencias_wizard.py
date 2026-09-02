# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo import models, fields

from ..models.hr_attendance import TZ


class AlertaInasistenciasWizard(models.TransientModel):
    _name = 'alerta.inasistencias.wizard'
    _description = 'Enviar Alerta de Inasistencias ahora'

    fecha_objetivo_sel = fields.Selection(
        selection=[
            ('hoy', 'Hoy (igual que las alertas de 07:00 / 14:00 / 23:15)'),
            ('ayer', 'Ayer, día completo (igual que el resumen de las 06:30)'),
        ],
        string='Fecha a evaluar',
        default='hoy',
        required=True,
        help=(
            "Elige 'Hoy' para disparar manualmente el mismo reporte que "
            "corren las 3 alertas programadas del día, o 'Ayer' para "
            "disparar manualmente el mismo resumen consolidado que corre "
            "todos los días a las 06:30."
        ),
    )

    def action_enviar_ahora(self):
        """Dispara ejecutar_alerta_inasistencias() de inmediato, fuera de
        los horarios programados — mismo motor que usan los 4 ir.cron."""
        self.ensure_one()

        fecha_objetivo = None
        if self.fecha_objetivo_sel == 'ayer':
            # Mismo cálculo de "ayer" que usa el cron del resumen de 06:30.
            fecha_objetivo = datetime.now(TZ).date() - timedelta(days=1)

        resultado = self.env['hr.attendance'].sudo().ejecutar_alerta_inasistencias(
            fecha_objetivo=fecha_objetivo,
        )

        total = len(resultado['reporte']['inasistencias'])
        enviado = resultado['correo_enviado']

        if enviado:
            mensaje = f"Reporte generado y correo enviado. Total inasistencias: {total}."
            tipo = 'success'
        else:
            mensaje = (
                f"Reporte generado (total inasistencias: {total}), pero el correo NO "
                f"se envió. Revisa que el Parámetro del Sistema "
                f"'alerta_inasistencia.correo_rrhh' esté configurado (Ajustes > Técnico > "
                f"Parámetros del sistema), o revisa el log del servidor para el detalle "
                f"del error."
            )
            tipo = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Alerta de Inasistencias',
                'message': mensaje,
                'sticky': not enviado,
                'type': tipo,
            },
        }
