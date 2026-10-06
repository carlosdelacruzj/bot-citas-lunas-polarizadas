from __future__ import annotations

from appointment_bot.browser.whatsapp.manager import _MANAGER


def prepare_whatsapp_web_draft(draft: dict[str, object]) -> dict[str, object]:
    return _MANAGER.prepare(draft)


def validate_whatsapp_web_session() -> dict[str, object]:
    return _MANAGER.prepare(
        {
            "action": "validate_session",
            "headless": True,
            "close_on_error": False,
            "disable_closed_target_retry": True,
        }
    )


def prepare_whatsapp_web_album(
    confirmation_draft: dict[str, object],
    payment_draft: dict[str, object],
    *,
    auto_send: bool = False,
) -> dict[str, object]:
    album_draft = {
        **confirmation_draft,
        "album_items": [confirmation_draft, payment_draft],
        "auto_send": auto_send,
        "close_on_error": False,
        "disable_closed_target_retry": auto_send,
        "headless": auto_send,
    }
    return _MANAGER.prepare(album_draft)


def prepare_whatsapp_web_documents(draft: dict[str, object]) -> dict[str, object]:
    document_draft = {
        **draft,
        "document_items": list(draft["attachment_paths"]),
        "disable_closed_target_retry": True,
        "close_on_error": True,
        "auto_send": True,
        "headless": True,
    }
    return _MANAGER.prepare(document_draft)


def send_whatsapp_web_daily_slot_summary(
    *,
    message_id: str,
    recipient_phone: str,
    message_text: str,
    publication_text: str,
    attachment_paths: list[str],
) -> dict[str, object]:
    return _MANAGER.prepare(
        {
            "action": "daily_slot_summary",
            "message_id": message_id,
            "recipient_phone": recipient_phone,
            "message_text": message_text,
            "publication_text": publication_text,
            "attachment_paths": attachment_paths,
            "disable_closed_target_retry": True,
            "close_on_error": True,
            "headless": True,
        }
    )


def send_whatsapp_web_registration_notice(
    *,
    message_id: str,
    recipient_phone: str | None,
    recipient_username: str | None,
    message_text: str,
) -> dict[str, object]:
    return _MANAGER.prepare(
        {
            "action": "registration_notice",
            "message_id": message_id,
            "recipient_phone": recipient_phone,
            "recipient_username": recipient_username,
            "message_text": message_text,
            "disable_closed_target_retry": True,
            "close_on_error": True,
            "headless": True,
        }
    )


def send_whatsapp_web_appointment_reminder(
    *,
    message_id: str,
    recipient_phone: str | None,
    recipient_username: str | None,
    message_text: str,
) -> dict[str, object]:
    return _MANAGER.prepare(
        {
            "action": "appointment_reminder",
            "message_id": message_id,
            "recipient_phone": recipient_phone,
            "recipient_username": recipient_username,
            "message_text": message_text,
            "disable_closed_target_retry": True,
            "close_on_error": True,
            "headless": True,
        }
    )
