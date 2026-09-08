from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext

from appointment_bot.browser.whatsapp.attachments import _attach_document
from appointment_bot.browser.whatsapp.common import _result, logger
from appointment_bot.browser.whatsapp.composition import _fill_caption
from appointment_bot.browser.whatsapp.evidence import (
    _safe_whatsapp_artifact_name,
    _save_whatsapp_debug_screenshot,
)
from appointment_bot.browser.whatsapp.navigation import _open_recipient_chat
from appointment_bot.browser.whatsapp.sending import _click_send_button, _send_plain_text_message
from appointment_bot.browser.whatsapp.session import _fresh_whatsapp_page


def _prepare_documents(context: BrowserContext, draft: dict[str, object]) -> dict[str, object]:
    page = _fresh_whatsapp_page(context)
    message_id = str(draft["message_id"])
    recipient_error = _open_recipient_chat(
        page, draft, message_id, "whatsapp-followup-chat-not-ready"
    )
    if recipient_error is not None:
        return recipient_error
    attachments = [Path(str(item)).resolve() for item in draft["document_items"]]
    if not all(path.is_file() for path in attachments):
        raise FileNotFoundError("Uno de los PDFs preparados ya no esta disponible.")
    _attach_document(page, attachments)
    if draft.get("auto_send"):
        documents_confirmed = _click_send_button(page, attachments)
        text_sent = _send_plain_text_message(
            page,
            str(draft["caption"]),
            evidence_prefix=(
                "whatsapp-followup-"
                f"{_safe_whatsapp_artifact_name(message_id)}"
            ),
        )
        delivery_components = {
            "documents": "confirmed" if documents_confirmed else "uncertain",
            "payment_confirmation": "confirmed" if text_sent else "uncertain",
        }
        if not documents_confirmed or not text_sent:
            evidence_path = _save_whatsapp_debug_screenshot(
                page,
                (
                    "whatsapp-followup-"
                    f"{_safe_whatsapp_artifact_name(message_id)}-components-uncertain"
                ),
            )
            logger.warning(
                "WhatsApp Web follow-up was not fully confirmed: "
                "message_id=%s documents_confirmed=%s text_confirmed=%s",
                message_id,
                documents_confirmed,
                text_sent,
            )
            if documents_confirmed:
                message = (
                    "Los PDFs salieron, pero WhatsApp no confirmo el texto post-pago. "
                    "No se marcara el paquete completo como enviado ni se reintentara "
                    "automaticamente."
                )
            elif text_sent:
                message = (
                    "WhatsApp cerro la vista previa de los PDFs sin permitir confirmar "
                    "automaticamente todas sus burbujas. El mensaje de pago confirmado "
                    "si fue enviado y confirmado; no se repetiran los PDFs."
                )
            else:
                message = (
                    "WhatsApp cerro la vista previa de los PDFs sin permitir confirmar "
                    "automaticamente todas sus burbujas y tampoco confirmo el mensaje "
                    "de pago. No se reintentara automaticamente."
                )
            if documents_confirmed:
                delivery_phase = "documents_confirmed_text_unconfirmed"
            elif text_sent:
                delivery_phase = "documents_unconfirmed_text_confirmed"
            else:
                delivery_phase = "documents_and_text_unconfirmed"
            return _result(
                "send_uncertain",
                message,
                message_id=message_id,
                draft_mode="documents",
                manual_send_required=True,
                delivery_phase=delivery_phase,
                evidence_path=evidence_path,
                delivery_components=delivery_components,
            )
        sent_evidence_path = _save_whatsapp_debug_screenshot(
            page,
            f"whatsapp-followup-{_safe_whatsapp_artifact_name(message_id)}-sent",
        )
        context.close()
        logger.info(
            "WhatsApp Web follow-up sent automatically: message_id=%s documents=%s",
            message_id,
            len(attachments),
        )
        return _result(
            "sent",
            "PDFs y texto post-pago enviados automaticamente.",
            message_id=message_id,
            draft_mode="documents",
            manual_send_required=False,
            sent=True,
            delivery_phase="confirmation_observed",
            evidence_path=sent_evidence_path,
            delivery_components=delivery_components,
        )
    draft_mode = _fill_caption(
        page,
        str(draft["caption"]),
        require_full_match=True,
        allow_footer_editor=True,
        trust_inserted_text=True,
    )
    if draft_mode != "caption":
        _save_whatsapp_debug_screenshot(page, "whatsapp-followup-caption-not-ready")
        raise RuntimeError(
            "WhatsApp no permitio unir el texto a los documentos; "
            "el borrador no se considera listo."
        )
    ready_screenshot = Path(".runtime/whatsapp-followup-ready.png").resolve()
    ready_screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ready_screenshot))
    logger.info(
        "WhatsApp Web follow-up ready: message_id=%s documents=%s",
        message_id,
        len(attachments),
    )
    return _result(
        "draft_ready",
        "PDFs y texto post-pago listos. Revisa WhatsApp y pulsa Enviar una sola vez.",
        message_id=message_id,
        draft_mode="documents",
    )
