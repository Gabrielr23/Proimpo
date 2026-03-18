import logging
import threading

import odoo
from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_send_edi_batch(self):
        """
        Envía a la DIAN los documentos EDI seleccionados en la vista lista,
        procesando en segundo plano para no bloquear la interfaz del usuario.
        """
        # Filtrar solo documentos con EDI pendiente de envío
        moves_to_process = self.filtered(
            lambda m: any(
                doc.state == 'to_send'
                for doc in m.edi_document_ids
            )
        )

        if not moves_to_process:
            raise UserError(_(
                'No hay documentos pendientes de envío a la DIAN en la selección.\n'
                'Solo se procesan documentos que aún no han sido enviados o que '
                'tienen un envío pendiente.'
            ))

        move_ids = moves_to_process.ids
        dbname = self.env.cr.dbname
        uid = self.env.uid

        _logger.info(
            'Lote EDI: iniciando envío de %d documentos en segundo plano. '
            'IDs: %s',
            len(move_ids), move_ids
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
                    '%d documentos se están enviando a la DIAN en segundo plano. '
                    'Revise el chatter de cada factura para ver el resultado.'
                ) % len(move_ids),
                'type': 'info',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    @staticmethod
    def _send_edi_batch_thread(dbname, uid, move_ids):
        """
        Hilo de fondo: itera sobre cada factura y llama al método estándar
        de Odoo para procesar el EDI. Cada factura se confirma por separado
        para aislar errores.
        """
        success_ids = []
        error_ids = []

        for move_id in move_ids:
            try:
                with odoo.registry(dbname).cursor() as cr:
                    env = odoo.api.Environment(cr, uid, {})
                    move = env['account.move'].browse(move_id)
                    move.action_process_edi_web_services()
                    cr.commit()
                    success_ids.append(move_id)
                    _logger.info(
                        'Lote EDI: account.move(%d) enviado correctamente.',
                        move_id
                    )
            except Exception:
                error_ids.append(move_id)
                _logger.exception(
                    'Lote EDI: error al enviar account.move(%d).',
                    move_id
                )

        _logger.info(
            'Lote EDI finalizado — Exitosos: %d %s | Con error: %d %s',
            len(success_ids), success_ids,
            len(error_ids), error_ids,
        )
