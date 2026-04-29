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
        Envía a la DIAN los documentos EDI seleccionados en la vista lista.

        Soporta dos frameworks según el proveedor configurado:
        - Servicio Gratuito DIAN (Odoo 18+): usa account.move.send.
          El estado pendiente se detecta por ausencia de CUFE/CUDE.
        - Carvajal (framework antiguo): usa edi_document_ids + state='to_send'.
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
            'Lote EDI (DIAN Gratuito): iniciando envío de %d documentos '
            'en segundo plano. IDs: %s',
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
    # Helpers estáticos (usados en el hilo de fondo)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_pending_edi(move):
        """
        Devuelve True si el documento está listo para enviar a la DIAN.

        Reglas:
        1. Debe estar confirmado (state == 'posted').
        2. Si ya tiene CUFE/CUDE asignado → ya fue validado por DIAN → excluir.
        3. Todo documento posted sin CUFE/CUDE se considera pendiente.

        Nota sobre el campo l10n_co_edi_cufe_cude:
        - Si el campo existe y tiene valor ('ABC123...'): ya enviado → False.
        - Si el campo existe y está vacío (False / ''):   pendiente  → True.
        - Si el campo NO existe en el modelo (None):      pendiente  → True.
          (Usar `not cufe` cubre los tres casos correctamente.)
        """
        if move.state != 'posted':
            return False

        cufe = getattr(move, 'l10n_co_edi_cufe_cude', None)
        if cufe:          # Tiene valor → DIAN ya lo validó → excluir
            return False

        return True       # posted + sin CUFE → pendiente de envío

    @staticmethod
    def _send_edi_batch_thread(dbname, uid, move_ids):
        """
        Hilo de fondo: procesa cada documento en su propia transacción
        para aislar errores y evitar bloqueos mutuos.
        """
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
                    _logger.info(
                        'Lote EDI: account.move(%d) enviado correctamente.',
                        move_id,
                    )
            except Exception:
                error_ids.append(move_id)
                _logger.exception(
                    'Lote EDI: error al procesar account.move(%d).',
                    move_id,
                )

        _logger.info(
            'Lote EDI finalizado — Exitosos: %d %s | Con error: %d %s',
            len(success_ids), success_ids,
            len(error_ids), error_ids,
        )

    @staticmethod
    def _send_single_edi(move, env):
        """
        Elige el método de envío apropiado según el framework disponible.

        Framework antiguo (Carvajal):
            Usa edi_document_ids + action_process_edi_web_services().

        Nuevo framework (Servicio Gratuito DIAN, Odoo 17/18):
            Usa account.move.send, que es el mismo mecanismo que invoca el
            botón "Enviar Documento Soporte a la DIAN" del formulario.
            Se crea el wizard programáticamente, deshabilitando el envío de
            email para no saturar buzones en un envío masivo.
        """
        # — Framework antiguo (Carvajal) —
        if move.edi_document_ids and any(
            d.state == 'to_send' for d in move.edi_document_ids
        ):
            _logger.info(
                'Lote EDI: move %d → framework antiguo (edi_document_ids).',
                move.id,
            )
            move.action_process_edi_web_services()
            return

        # — Servicio Gratuito DIAN (account.move.send) —
        _logger.info(
            'Lote EDI: move %d → account.move.send (Servicio Gratuito DIAN).',
            move.id,
        )
        send_model = env['account.move.send']
        wizard_vals = {
            'move_ids': [Command.set([move.id])],
        }

        # Deshabilitar envío de email en el lote (si el campo existe en esta
        # versión de Odoo) para no generar correos masivos innecesarios.
        if 'send_mail' in send_model._fields:
            wizard_vals['send_mail'] = False

        wizard = send_model.create(wizard_vals)

        # action_send_and_print() en el wizard ejecuta el envío real
        # (es el handler del botón "Enviar" dentro del wizard).
        # El valor de retorno es un ir.action que ignoramos en segundo plano.
        wizard.action_send_and_print()
