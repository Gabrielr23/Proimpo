import logging
import threading

import odoo
from odoo import Command, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_send_edi_batch(self):
        """
        Envía a la DIAN los documentos EDI seleccionados en la vista lista
        usando el Servicio Gratuito de Odoo (Odoo 18+).
        """
        moves_to_process = self.filtered(AccountMove._is_pending_edi)

        if not moves_to_process:
            raise UserError(_(
                'No hay documentos válidos para enviar a la DIAN en la selección.\n\n'
                'Verifique que los documentos seleccionados:\n'
                '  • Estén confirmados (publicados, no en borrador).\n'
                '  • No hayan sido ya validados por la DIAN (con CUFE/CUDE).'
            ))

        move_ids = moves_to_process.ids
        dbname = self.env.cr.dbname
        uid = self.env.uid

        _logger.info(
            'Lote EDI: iniciando envío de %d documentos en segundo plano. IDs: %s',
            len(move_ids), move_ids,
        )

        thread = threading.Thread(
            target=AccountMove._send_edi_batch_thread,
            args=(dbname, uid, move_ids),
            daemon=True,
        )
        thread.start()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Envío en proceso'),
                'message': _(
                    '%d documentos se están enviando a la DIAN (Servicio Gratuito) '
                    'en segundo plano. '
                    'Revise el chatter de cada documento para ver el resultado.'
                ) % len(move_ids),
                'type': 'info',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    # ------------------------------------------------------------------
    # Filtro
    # ------------------------------------------------------------------

    @staticmethod
    def _is_pending_edi(move):
        """
        True si el documento está publicado y aún no tiene CUFE/CUDE de la DIAN.

        l10n_co_edi_cufe_cude:
          - Campo inexistente (None) → incluir (estado desconocido).
          - Campo vacío (False / '')  → incluir (pendiente de envío).
          - Campo con valor           → excluir (ya validado por DIAN).
        """
        if move.state != 'posted':
            return False
        cufe = getattr(move, 'l10n_co_edi_cufe_cude', None)
        return not cufe   # None, False o '' son pendientes; un valor real excluye

    # ------------------------------------------------------------------
    # Hilo de fondo
    # ------------------------------------------------------------------

    @staticmethod
    def _send_edi_batch_thread(dbname, uid, move_ids):
        """Procesa cada documento en su propia transacción para aislar errores."""
        success_ids = []
        error_ids = []

        for move_id in move_ids:
            try:
                with odoo.registry(dbname).cursor() as cr:
                    env = odoo.api.Environment(cr, uid, {})
                    move = env['account.move'].browse(move_id)

                    AccountMove._send_single_edi(move, env)
                    cr.commit()

                    success_ids.append(move_id)
                    _logger.info('Lote EDI: move(%d) procesado correctamente.', move_id)

            except Exception:
                error_ids.append(move_id)
                _logger.exception('Lote EDI: error procesando move(%d).', move_id)

        _logger.info(
            'Lote EDI finalizado — Exitosos: %d %s | Con error: %d %s',
            len(success_ids), success_ids,
            len(error_ids), error_ids,
        )

    # ------------------------------------------------------------------
    # Lógica de envío — detección automática del método correcto
    # ------------------------------------------------------------------

    @staticmethod
    def _send_single_edi(move, env):
        """
        Detecta y llama el método de envío apropiado para este move.

        Estrategia (en orden):
        1. Framework antiguo (Carvajal): edi_document_ids con state='to_send'.
        2. Método específico l10n_co_edi si existe en el modelo (p. ej. Odoo Enterprise).
        3. account.move.send con contexto completo (Odoo 17/18 nuevo framework).

        También registra información de diagnóstico en el log para facilitar
        la identificación del método correcto si ninguno funciona.
        """
        # ── 1. Framework antiguo (Carvajal) ──────────────────────────────
        if move.edi_document_ids and any(
            d.state == 'to_send' for d in move.edi_document_ids
        ):
            _logger.info('Lote EDI move(%d): usando framework antiguo.', move.id)
            move.action_process_edi_web_services()
            return

        # ── Diagnóstico: métodos l10n_co disponibles ──────────────────────
        available_l10n = sorted(
            m for m in dir(type(move))
            if 'l10n_co' in m and not m.startswith('__')
        )
        _logger.info(
            'Lote EDI move(%d): atributos l10n_co en account.move → %s',
            move.id, available_l10n,
        )

        # ── 2. Método directo del módulo l10n_co_edi (Enterprise) ─────────
        # Odoo Enterprise suele exponer un método público específico para el
        # botón "Enviar Documento Soporte a la DIAN".  Probamos los nombres
        # más comunes según los patrones de nomenclatura de Odoo 17/18.
        direct_method_candidates = [
            'action_l10n_co_edi_send',
            'action_l10n_co_edi_send_document',
            'l10n_co_action_send_to_dian',
            'button_l10n_co_edi_send',
            'action_send_edi_to_dian',
        ]
        for method_name in direct_method_candidates:
            method = getattr(move, method_name, None)
            if callable(method):
                _logger.info(
                    'Lote EDI move(%d): método directo encontrado → %s',
                    move.id, method_name,
                )
                method()
                return

        # ── 3. account.move.send (nuevo framework Odoo 17/18) ────────────
        _logger.info(
            'Lote EDI move(%d): usando account.move.send con contexto.',
            move.id,
        )
        send_model = env['account.move.send'].with_context(
            active_ids=[move.id],
            active_id=move.id,
            active_model='account.move',
        )

        wizard_vals = {'move_ids': [Command.set([move.id])]}
        if 'send_mail' in send_model._fields:
            wizard_vals['send_mail'] = False

        wizard = send_model.create(wizard_vals)

        # Diagnóstico: registrar todos los campos del wizard relacionados con
        # EDI/envío para entender qué opciones están activas.
        relevant_wizard_fields = {
            fname: getattr(wizard, fname, '?')
            for fname in sorted(wizard._fields)
            if any(k in fname for k in ('edi', 'send', 'dian', 'l10n', 'print', 'co_'))
        }
        _logger.info(
            'Lote EDI move(%d): wizard(%d) campos relevantes → %s',
            move.id, wizard.id, relevant_wizard_fields,
        )

        result = wizard.action_send_and_print()
        _logger.info(
            'Lote EDI move(%d): resultado de action_send_and_print → %s',
            move.id, result,
        )

        # Verificar si se asignó el CUFE tras el envío
        move.invalidate_recordset(['l10n_co_edi_cufe_cude'])
        cufe_after = getattr(move, 'l10n_co_edi_cufe_cude', None)
        _logger.info(
            'Lote EDI move(%d): CUFE/CUDE tras envío → %s',
            move.id, cufe_after or '⚠ SIN ASIGNAR',
        )
