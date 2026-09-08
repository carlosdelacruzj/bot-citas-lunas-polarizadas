from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext

from appointment_bot.browser.whatsapp.album import _send_album
from appointment_bot.browser.whatsapp.attachments import _attach_image
from appointment_bot.browser.whatsapp.common import (
    DAILY_SUMMARY_IMAGE_BATCH_SIZE,
    WhatsAppSendUncertain,
    _result,
)
from appointment_bot.browser.whatsapp.dom import _album_thumbnails
from appointment_bot.browser.whatsapp.evidence import (
    _safe_whatsapp_artifact_name,
    _save_whatsapp_debug_screenshot,
)
from appointment_bot.browser.whatsapp.navigation import (
    _chat_not_ready_result,
    _open_recipient_chat,
    _wait_for_chat,
)
from appointment_bot.browser.whatsapp.sending import _send_plain_text_message
from appointment_bot.browser.whatsapp.session import _fresh_whatsapp_page


def _send_daily_slot_summary(
    context: BrowserContext,
    draft: dict[str, object],
) -> dict[str, object]:
    attachments = [
        Path(str(path)).resolve()
        for path in list(draft.get("attachment_paths") or [])
    ]
    if attachments and not all(path.is_file() for path in attachments):
        raise FileNotFoundError(
            "Una de las imagenes marcadas del resumen diario ya no esta disponible."
        )

    page = _fresh_whatsapp_page(context)
    phone = "".join(
        character
        for character in str(draft["recipient_phone"])
        if character.isdigit()
    )
    message_id = str(draft["message_id"])
    evidence_id = _safe_whatsapp_artifact_name(message_id)
    target = f"https://web.whatsapp.com/send?phone={phone}"
    page.goto(target, wait_until="domcontentloaded", timeout=45_000)
    if not _wait_for_chat(page):
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name="whatsapp-daily-summary-chat-not-ready",
        )

    delivery_components = {
        "summary": "not_attempted",
        "images": "not_attempted" if attachments else "skipped",
        "publication": "not_attempted",
    }
    message_text = str(draft["message_text"])
    if message_text:
        text_sent = _send_plain_text_message(
            page,
            message_text,
            evidence_prefix=f"whatsapp-daily-summary-{evidence_id}-summary",
        )
        if not text_sent:
            delivery_components["summary"] = "uncertain"
            return _result(
                "send_uncertain",
                "WhatsApp no confirmo el mensaje del resumen diario.",
                message_id=message_id,
                delivery_phase="send_attempted",
                evidence_path=(
                    f".runtime/whatsapp-daily-summary-{evidence_id}-summary-"
                    "text-send-uncertain.png"
                ),
                delivery_components=delivery_components,
            )
        delivery_components["summary"] = "confirmed"
    else:
        delivery_components["summary"] = "skipped"

    if attachments:
        batches = [
            attachments[index : index + DAILY_SUMMARY_IMAGE_BATCH_SIZE]
            for index in range(0, len(attachments), DAILY_SUMMARY_IMAGE_BATCH_SIZE)
        ]
        confirmed_image_count = 0
        for batch_number, batch in enumerate(batches, start=1):
            batch_evidence_id = f"{evidence_id}-batch-{batch_number}-of-{len(batches)}"
            _attach_image(page, batch)
            page.wait_for_timeout(1_000)
            if len(_album_thumbnails(page)) != len(batch):
                _save_whatsapp_debug_screenshot(
                    page,
                    f"whatsapp-daily-summary-images-not-ready-{batch_evidence_id}",
                )
                raise RuntimeError(
                    "WhatsApp no mostro todas las imagenes del paquete "
                    f"{batch_number} de {len(batches)}."
                )
            _save_whatsapp_debug_screenshot(
                page,
                f"whatsapp-daily-summary-before-send-{batch_evidence_id}",
            )
            try:
                _send_album(
                    page,
                    expected_count=len(batch),
                    uncertain_screenshot_name=(
                        "whatsapp-daily-summary-upload-uncertain-"
                        f"{batch_evidence_id}"
                    ),
                )
            except WhatsAppSendUncertain as exc:
                delivery_components["images"] = "uncertain"
                context.close()
                return _result(
                    "send_uncertain",
                    (
                        f"{exc} Paquete {batch_number} de {len(batches)}; "
                        f"{confirmed_image_count} de {len(attachments)} "
                        "imagenes confirmadas antes de detener el envio."
                    ),
                    message_id=message_id,
                    delivery_phase="interaction_started",
                    evidence_path=exc.evidence_path,
                    delivery_components=delivery_components,
                )
            confirmed_image_count += len(batch)
            _save_whatsapp_debug_screenshot(
                page,
                f"whatsapp-daily-summary-images-sent-{batch_evidence_id}",
            )
        delivery_components["images"] = "confirmed"

    publication_sent = _send_plain_text_message(
        page,
        str(draft["publication_text"]),
        evidence_prefix=f"whatsapp-daily-summary-{evidence_id}-publication",
    )
    if not publication_sent:
        delivery_components["publication"] = "uncertain"
        return _result(
            "send_uncertain",
            "WhatsApp no confirmo la publicacion diaria para TikTok.",
            message_id=message_id,
            delivery_phase="send_attempted",
            evidence_path=(
                f".runtime/whatsapp-daily-summary-{evidence_id}-publication-"
                "text-send-uncertain.png"
            ),
            delivery_components=delivery_components,
        )
    delivery_components["publication"] = "confirmed"
    sent_evidence_path = _save_whatsapp_debug_screenshot(
        page,
        "whatsapp-daily-summary-sent",
    )
    context.close()
    return _result(
        "sent",
        (
            "Resumen diario, imagenes y publicacion de TikTok "
            "enviados automaticamente."
        ),
        message_id=message_id,
        sent=True,
        delivery_phase="confirmation_observed",
        evidence_path=sent_evidence_path,
        delivery_components=delivery_components,
    )


def _send_registration_notice(
    context: BrowserContext,
    draft: dict[str, object],
) -> dict[str, object]:
    page = _fresh_whatsapp_page(context)
    message_id = str(draft["message_id"])
    evidence_id = _safe_whatsapp_artifact_name(message_id)
    recipient_error = _open_recipient_chat(
        page, draft, message_id, "whatsapp-registration-notice-chat-not-ready"
    )
    if recipient_error is not None:
        return recipient_error
    if not _send_plain_text_message(
        page,
        str(draft["message_text"]),
        evidence_prefix=f"whatsapp-registration-notice-{evidence_id}",
    ):
        return _result(
            "send_uncertain",
            "WhatsApp no confirmo el aviso automatico de registro.",
            message_id=message_id,
            delivery_phase="send_attempted",
            evidence_path=(
                f".runtime/whatsapp-registration-notice-{evidence_id}-"
                "text-send-uncertain.png"
            ),
        )
    sent_evidence_path = _save_whatsapp_debug_screenshot(
        page,
        f"whatsapp-registration-notice-sent-{evidence_id}",
    )
    context.close()
    return _result(
        "sent",
        "Aviso automatico de registro enviado.",
        message_id=message_id,
        sent=True,
        delivery_phase="confirmation_observed",
        evidence_path=sent_evidence_path,
    )


def _send_appointment_reminder(
    context: BrowserContext,
    draft: dict[str, object],
) -> dict[str, object]:
    page = _fresh_whatsapp_page(context)
    message_id = str(draft["message_id"])
    evidence_id = _safe_whatsapp_artifact_name(message_id)
    recipient_error = _open_recipient_chat(
        page, draft, message_id, "whatsapp-appointment-reminder-chat-not-ready"
    )
    if recipient_error is not None:
        return recipient_error
    if not _send_plain_text_message(
        page,
        str(draft["message_text"]),
        evidence_prefix=f"whatsapp-appointment-reminder-{evidence_id}",
    ):
        return _result(
            "send_uncertain",
            "WhatsApp no confirmo el recordatorio automatico de cita.",
            message_id=message_id,
            delivery_phase="send_attempted",
            evidence_path=(
                f".runtime/whatsapp-appointment-reminder-{evidence_id}-"
                "text-send-uncertain.png"
            ),
        )
    sent_evidence_path = _save_whatsapp_debug_screenshot(
        page,
        f"whatsapp-appointment-reminder-sent-{evidence_id}",
    )
    context.close()
    return _result(
        "sent",
        "Recordatorio automatico de cita enviado.",
        message_id=message_id,
        sent=True,
        delivery_phase="confirmation_observed",
        evidence_path=sent_evidence_path,
    )
