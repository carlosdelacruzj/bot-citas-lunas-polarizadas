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
from appointment_bot.browser.whatsapp.progress import (
    confirm_components,
    plan_delivery,
    selected_components,
)
from appointment_bot.browser.whatsapp.safety import require_clear_outgoing_queue
from appointment_bot.browser.whatsapp.sending import _click_send_button, _send_plain_text_message
from appointment_bot.browser.whatsapp.session import _fresh_whatsapp_page


def _prepare_documents(context: BrowserContext, draft: dict[str, object]) -> dict[str, object]:
    all_attachments = [Path(str(item)).resolve() for item in draft["document_items"]]
    document_keys = [f"document:{index}" for index in range(len(all_attachments))]
    plan_delivery(
        draft,
        list(zip(document_keys, [path.name for path in all_attachments], strict=True))
        + [("payment_confirmation", "Texto postpago")],
    )
    chosen = selected_components(document_keys + ["payment_confirmation"])
    page = _fresh_whatsapp_page(context)
    message_id = str(draft["message_id"])
    recipient_error = _open_recipient_chat(
        page, draft, message_id, "whatsapp-followup-chat-not-ready"
    )
    if recipient_error is not None:
        return recipient_error
    require_clear_outgoing_queue(
        page, evidence_prefix=f"whatsapp-followup-{_safe_whatsapp_artifact_name(message_id)}"
    )
    attachments = [
        path for key, path in zip(document_keys, all_attachments, strict=True) if key in chosen
    ]
    document_keys = [key for key in document_keys if key in chosen]
    if not all(path.is_file() for path in attachments):
        raise FileNotFoundError("Uno de los PDFs preparados ya no esta disponible.")
    if draft.get("auto_send"):
        text_sent = "payment_confirmation" not in chosen or _send_plain_text_message(
            page,
            str(draft["caption"]),
            component_keys=["payment_confirmation"],
            evidence_prefix=(f"whatsapp-followup-{_safe_whatsapp_artifact_name(message_id)}"),
        )
        if not text_sent:
            evidence_path = _save_whatsapp_debug_screenshot(
                page,
                f"whatsapp-followup-{_safe_whatsapp_artifact_name(message_id)}-text-unconfirmed",
            )
            return _result(
                "send_uncertain",
                "No se observo confirmacion del texto post-pago dentro del plazo; "
                "puede haberse enviado. No se iniciaron los PDFs pendientes. "
                "Revisa el chat antes de recuperar; no se reintentara automaticamente.",
                message_id=message_id,
                draft_mode="documents",
                manual_send_required=True,
                delivery_phase="text_unconfirmed_documents_not_attempted",
                evidence_path=evidence_path,
                delivery_components={
                    "documents": "not_attempted" if attachments else "confirmed",
                    "payment_confirmation": "uncertain",
                },
            )
        if attachments:
            require_clear_outgoing_queue(
                page,
                evidence_prefix=f"whatsapp-followup-{_safe_whatsapp_artifact_name(message_id)}",
            )
            _attach_document(page, attachments)
        documents_confirmed = not attachments or _click_send_button(
            page, attachments, component_keys=document_keys
        )
        if attachments and documents_confirmed:
            confirm_components(document_keys)
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
            message = (
                "El texto post-pago fue confirmado, pero no se pudo confirmar "
                "la salida de todos los PDFs. Revisa el chat antes de recuperar; "
                "no se repetiran automaticamente."
            )
            delivery_phase = "documents_unconfirmed_text_confirmed"
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
    if attachments:
        _attach_document(page, attachments)
    draft_mode = _fill_caption(
        page,
        str(draft["caption"]),
        require_full_match=True,
        allow_footer_editor=True,
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
