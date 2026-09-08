from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Page

from appointment_bot.browser.whatsapp.attachments import _attach_image
from appointment_bot.browser.whatsapp.common import (
    WhatsAppSendUncertain,
    _AttachmentBeforeFileSelectionError,
    _result,
    logger,
)
from appointment_bot.browser.whatsapp.composition import _fill_selected_album_caption
from appointment_bot.browser.whatsapp.confirmation import (
    _outgoing_image_message_records,
    _wait_until_outgoing_images_uploaded,
)
from appointment_bot.browser.whatsapp.dom import (
    _album_control_summary,
    _album_thumbnails,
    _normal_chat_composer_visible,
)
from appointment_bot.browser.whatsapp.evidence import (
    _safe_whatsapp_artifact_name,
    _save_whatsapp_debug_screenshot,
)
from appointment_bot.browser.whatsapp.navigation import _open_recipient_chat
from appointment_bot.browser.whatsapp.sending import _click_visible_send_button
from appointment_bot.browser.whatsapp.session import _fresh_whatsapp_page


def _prepare_album(context: BrowserContext, draft: dict[str, object]) -> dict[str, object]:
    items = list(draft["album_items"])
    if len(items) != 2:
        raise ValueError("El album de WhatsApp requiere exactamente dos imagenes.")
    attachments = [Path(str(item["attachment_path"])).resolve() for item in items]
    if not all(path.is_file() for path in attachments):
        raise FileNotFoundError("Una de las imagenes preparadas ya no esta disponible.")
    page_or_error = _attach_album_with_safe_page_retry(context, draft, attachments)
    if isinstance(page_or_error, dict):
        return page_or_error
    page = page_or_error
    page.wait_for_timeout(1_000)
    thumbnails = _album_thumbnails(page)
    if len(thumbnails) != len(items):
        logger.info("WhatsApp Web album controls: %s", _album_control_summary(page))
        raise RuntimeError("WhatsApp no mostro las dos miniaturas del album.")
    captions = [str(item["caption"]) for item in items]
    combined_caption = "\n\n".join(caption for caption in captions if caption.strip())
    caption_ready = True
    try:
        _fill_selected_album_caption(page, combined_caption)
    except RuntimeError:
        caption_ready = False
        _save_whatsapp_debug_screenshot(page, "whatsapp-album-caption-not-ready")
        logger.exception("Could not write WhatsApp album caption")
    if draft.get("auto_send"):
        if not caption_ready:
            raise RuntimeError(
                "WhatsApp no confirmo el texto del album; no se realizo el envio automatico."
            )
        _save_whatsapp_debug_screenshot(page, "whatsapp-album-before-send")
        message_id = str(draft["message_id"])
        evidence_id = _safe_whatsapp_artifact_name(message_id)
        try:
            _send_album(
                page,
                uncertain_screenshot_name=(
                    f"whatsapp-album-upload-uncertain-{evidence_id}"
                ),
            )
        except WhatsAppSendUncertain as exc:
            context.close()
            logger.warning(
                "WhatsApp Web album delivery is uncertain: message_id=%s",
                message_id,
            )
            return _result(
                "send_uncertain",
                str(exc),
                message_id=message_id,
                draft_mode="album",
                manual_send_required=True,
                sent=False,
                delivery_phase="interaction_started",
                evidence_path=exc.evidence_path,
            )
        sent_evidence_path = _save_whatsapp_debug_screenshot(
            page,
            "whatsapp-album-sent",
        )
        context.close()
        logger.info(
            "WhatsApp Web album sent automatically: message_id=%s items=%s",
            draft["message_id"],
            len(items),
        )
        return _result(
            "sent",
            "Constancia y cobro enviados automaticamente.",
            message_id=str(draft["message_id"]),
            draft_mode="album",
            manual_send_required=False,
            sent=True,
            delivery_phase="confirmation_observed",
            evidence_path=sent_evidence_path,
        )
    ready_screenshot = Path(".runtime/whatsapp-album-ready.png").resolve()
    ready_screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ready_screenshot))
    logger.info(
        "WhatsApp Web album ready: message_id=%s items=%s",
        draft["message_id"],
        len(items),
    )
    return _result(
        "draft_ready",
        (
            "Las dos imagenes y el texto quedaron listos. "
            "Revisa el album y pulsa Enviar una sola vez."
            if caption_ready
            else "Las dos imagenes quedaron cargadas. "
            "WhatsApp no confirmo el texto; revisa el album antes de enviar."
        ),
        message_id=str(draft["message_id"]),
        draft_mode="album",
    )


def _attach_album_with_safe_page_retry(
    context: BrowserContext,
    draft: dict[str, object],
    attachments: list[Path],
) -> Page | dict[str, object]:
    for page_attempt in range(1, 3):
        page = _fresh_whatsapp_page(context)
        recipient_error = _open_recipient_chat(
            page, draft, str(draft["message_id"]), "whatsapp-album-chat-not-ready"
        )
        if recipient_error is not None:
            return recipient_error
        try:
            _attach_image(page, attachments)
            return page
        except _AttachmentBeforeFileSelectionError:
            if page_attempt == 2:
                raise
            logger.info(
                "WhatsApp album safe page retry before file selection: "
                "message_id=%s",
                draft["message_id"],
            )
    raise RuntimeError("WhatsApp no pudo preparar el album despues del reintento seguro.")


def _send_album(
    page: Page,
    *,
    expected_count: int = 2,
    uncertain_screenshot_name: str = "whatsapp-album-upload-uncertain",
) -> None:
    if len(_album_thumbnails(page)) != expected_count:
        raise RuntimeError(
            "WhatsApp no mantuvo todas las miniaturas antes del envio."
        )
    initial_image_signatures = {
        signature for signature, _state in _outgoing_image_message_records(page)
    }
    viewport = page.viewport_size or {"width": 0, "height": 0}
    if not viewport["width"] or not viewport["height"]:
        raise RuntimeError("WhatsApp no informo el tamaño de la ventana para enviar el album.")
    if not _click_visible_send_button(page):
        page.mouse.click(viewport["width"] - 48, viewport["height"] - 50)
    deadline = time.monotonic() + 30
    next_send_retry_at = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not _album_thumbnails(page) and _normal_chat_composer_visible(page):
            page.wait_for_timeout(1_000)
            if not _album_thumbnails(page):
                if not _wait_until_outgoing_images_uploaded(
                    page,
                    initial_signatures=initial_image_signatures,
                    expected_count=expected_count,
                ):
                    evidence_path = _save_whatsapp_debug_screenshot(
                        page,
                        uncertain_screenshot_name,
                    )
                    raise WhatsAppSendUncertain(
                        "WhatsApp cerro la vista previa, pero no confirmo "
                        "la carga de todas las imagenes.",
                        evidence_path=evidence_path,
                    )
                return
        elif time.monotonic() >= next_send_retry_at:
            if not _click_visible_send_button(page):
                page.keyboard.press("Enter")
            elif _album_thumbnails(page):
                page.keyboard.press("Enter")
            next_send_retry_at = time.monotonic() + 2
        page.wait_for_timeout(500)
    evidence_path = _save_whatsapp_debug_screenshot(
        page,
        uncertain_screenshot_name,
    )
    raise WhatsAppSendUncertain(
        "WhatsApp no confirmo el envio del album; las miniaturas continuaron visibles.",
        evidence_path=evidence_path,
    )
