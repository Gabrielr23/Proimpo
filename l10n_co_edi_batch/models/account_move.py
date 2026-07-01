import base64
import io
import logging
import threading
import zipfile

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
        en segundo plano. Tras el envío exitoso adjunta un ZIP con el XML y el
        PDF de cada documento al chatter.
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
        """True si el documento está publicado y aún no tiene CUFE/CUDE de la DIAN."""
        if move.state != 'posted':
            return False
        cufe = getattr(move, 'l10n_co_edi_cufe_cude', None)
        return not cufe

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
                # 1. Enviar a la DIAN
                with odoo.modules.registry.Registry(dbname).cursor() as cr:
                    env = odoo.api.Environment(cr, uid, {})
                    move = env['account.move'].browse(move_id)
                    move.l10n_co_dian_action_send_bill_support_document()
                    cr.commit()

                success_ids.append(move_id)
                _logger.info('Lote EDI: move(%d) procesado correctamente.', move_id)

                # 2. Adjuntar ZIP (XML + PDF) al chatter en transacción separada
                AccountMove._attach_dian_zip(dbname, uid, move_id)

            except Exception:
                error_ids.append(move_id)
                _logger.exception('Lote EDI: error procesando move(%d).', move_id)

        _logger.info(
            'Lote EDI finalizado — Exitosos: %d %s | Con error: %d %s',
            len(success_ids), success_ids,
            len(error_ids), error_ids,
        )

    # ------------------------------------------------------------------
    # ZIP con XML DIAN + PDF
    # ------------------------------------------------------------------

    @staticmethod
    def _attach_dian_zip(dbname, uid, move_id):
        """
        Tras un envío exitoso, genera un ZIP con el XML adjuntado por la DIAN
        y el PDF del documento, y lo publica en el chatter.
        """
        try:
            with odoo.modules.registry.Registry(dbname).cursor() as cr:
                env = odoo.api.Environment(cr, uid, {})
                move = env['account.move'].browse(move_id)

                # ── XML: el servicio DIAN lo adjunta con nombre 'dian_<nombre>.xml' ──
                xml_attach = env['ir.attachment'].search([
                    ('res_model', '=', 'account.move'),
                    ('res_id', '=', move_id),
                    ('name', 'like', 'dian_'),
                ], order='id desc', limit=1)

                if not xml_attach:
                    _logger.warning(
                        'Lote EDI move(%d): XML DIAN no encontrado, omitiendo ZIP.',
                        move_id,
                    )
                    return

                # ── PDF: renderizar el informe de factura ──────────────────────────
                pdf_content = None
                try:
                    report = env.ref(
                        'account.action_account_invoice_from_invoice',
                        raise_if_not_found=False,
                    )
                    if report:
                        pdf_content, _ = report.sudo()._render_qweb_pdf(
                            res_ids=[move_id]
                        )
                except Exception:
                    _logger.warning(
                        'Lote EDI move(%d): no se pudo generar el PDF; el ZIP solo contendrá el XML.',
                        move_id, exc_info=True,
                    )

                # ── Construir ZIP en memoria ───────────────────────────────────────
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr(xml_attach.name, base64.b64decode(xml_attach.datas))
                    if pdf_content:
                        zf.writestr(f'{move.name}.pdf', pdf_content)

                # ── Crear adjunto y publicar en chatter ───────────────────────────
                zip_attach = env['ir.attachment'].create({
                    'name': f'dian_{move.name}.zip',
                    'type': 'binary',
                    'datas': base64.b64encode(zip_buffer.getvalue()).decode(),
                    'res_model': 'account.move',
                    'res_id': move_id,
                    'mimetype': 'application/zip',
                })

                move.message_post(
                    body=_('Envío DIAN en lote completado. ZIP con XML y PDF adjunto.'),
                    attachment_ids=[zip_attach.id],
                )
                cr.commit()
                _logger.info('Lote EDI move(%d): ZIP DIAN adjuntado al chatter.', move_id)

        except Exception:
            _logger.exception('Lote EDI move(%d): error generando ZIP DIAN.', move_id)
