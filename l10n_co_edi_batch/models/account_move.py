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
        Envía a la DIAN los Documentos Soporte seleccionados en la vista lista,
        usando el mismo método que el botón "Enviar Documento Soporte a la DIAN"
        (l10n_co_dian_action_send_bill_support_document), en segundo plano.
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

    @staticmethod
    def _is_pending_edi(move):
        """True si el documento está publicado y aún no tiene CUFE/CUDE de la DIAN."""
        if move.state != 'posted':
            return False
        cufe = getattr(move, 'l10n_co_edi_cufe_cude', None)
        return not cufe

    @staticmethod
    def _send_edi_batch_thread(dbname, uid, move_ids):
        """Procesa cada documento en su propia transacción para aislar errores."""
        success_ids = []
        error_ids = []

        for move_id in move_ids:
            try:
                with odoo.modules.registry.Registry(dbname).cursor() as cr:
                    env = odoo.api.Environment(cr, uid, {})
                    move = env['account.move'].browse(move_id)
                    move.l10n_co_dian_action_send_bill_support_document()
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
