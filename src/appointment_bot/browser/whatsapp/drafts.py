from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext

from appointment_bot.browser.whatsapp.album import _prepare_album
from appointment_bot.browser.whatsapp.attachments import _attach_image
from appointment_bot.browser.whatsapp.common import _result, logger
from appointment_bot.browser.whatsapp.composition import _fill_caption
from appointment_bot.browser.whatsapp.documents import _prepare_documents
from appointment_bot.browser.whatsapp.navigation import _open_recipient_chat
from appointment_bot.browser.whatsapp.notifications import (
    _send_appointment_reminder,
    _send_daily_slot_summary,
    _send_registration_notice,
)
from appointment_bot.browser.whatsapp.session import _validate_whatsapp_session


def _prepare_draft(context: BrowserContext, draft: dict[str, object]) -> dict[str, object]:
    if draft.get("action") == "validate_session":
        return _validate_whatsapp_session(context)
    if draft.get("action") == "daily_slot_summary":
        return _send_daily_slot_summary(context, draft)
    if draft.get("action") == "registration_notice":
        return _send_registration_notice(context, draft)
    if draft.get("action") == "appointment_reminder":
        return _send_appointment_reminder(context, draft)
    if draft.get("album_items"):
        return _prepare_album(context, draft)
    if draft.get("document_items"):
        return _prepare_documents(context, draft)
    page = context.pages[0] if context.pages else context.new_page()
    message_id = str(draft["message_id"])
    recipient_error = _open_recipient_chat(
        page, draft, message_id, "whatsapp-confirmation-chat-not-ready"
    )
    if recipient_error is not None:
        return recipient_error

    attachment = Path(str(draft["attachment_path"])).resolve()
    if not attachment.is_file():
        raise FileNotFoundError("La constancia preparada ya no esta disponible.")
    try:
        _attach_image(page, attachment)
    except RuntimeError as exc:
        if "control para adjuntar" not in str(exc):
            raise
        recipient_error = _open_recipient_chat(
            page, draft, message_id, "whatsapp-confirmation-chat-retry-not-ready"
        )
        if recipient_error is not None:
            raise RuntimeError(str(recipient_error["message"])) from exc
        _attach_image(page, attachment)
    draft_mode = _fill_caption(page, str(draft["caption"]))
    if draft_mode == "queued_text":
        recipient_error = _open_recipient_chat(
            page, draft, message_id, "whatsapp-confirmation-text-retry-not-ready"
        )
        if recipient_error is not None:
            raise RuntimeError(str(recipient_error["message"]))
        _attach_image(page, attachment)
        draft_mode = _fill_caption(page, str(draft["caption"]))
        if draft_mode != "caption":
            raise RuntimeError(
                "WhatsApp no permitio unir el texto a la imagen; el borrador no se considera listo."
            )
    logger.info(
        "WhatsApp Web draft ready: message_id=%s test_mode=%s",
        message_id,
        draft["test_mode"],
    )
    return _result(
        "draft_ready",
        (
            "Imagen y texto listos. Revisa la ventana de WhatsApp y pulsa Enviar manualmente."
            if draft_mode == "caption"
            else "La imagen esta lista y el texto quedo preparado detras de la vista previa. "
            "Envia primero la imagen y luego pulsa Enviar una segunda vez para el texto."
        ),
        message_id=message_id,
        draft_mode=draft_mode,
    )
