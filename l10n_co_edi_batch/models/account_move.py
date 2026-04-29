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
                'No hay documentos pendientes de envío a la DIAN en la selección.\n\n'
                'Verifique que los documentos:\n'
                '  • Estén confirmados (publicados).\n'
                '  • No hayan sido enviados ya (sin CUFE/CUDE asignado).'
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
        Devuelve True si el documento necesita ser enviado a la DIAN.

        Lógica:
        1. Debe estar confirmado (state == 'posted').
        2. Framework antiguo (Carvajal): edi_document_ids con state='to_send'.
        3. Servicio Gratuito DIAN (nuevo framework): campo l10n_co_edi_cufe_cude
           vacío indica que aún no se ha enviado/validado por la DIAN.
        """
        if move.state != 'posted':
            return False

        # — Framework antiguo (Carvajal) —
        if move.edi_document_ids:
            return any(doc.state == 'to_send' for doc in move.edi_document_ids)

        # — Servicio Gratuito DIAN —
        # El campo l10n_co_edi_cufe_cude (Char) lo agrega el módulo l10n_co_edi.
        # Vacío (False/'') = documento no enviado; con valor = ya validado por DIAN.
        cufe = getattr(move, 'l10n_co_edi_cufe_cude', None)
        return cufe is not None and not cufe

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
