from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("appointment_bot.browser.whatsapp_web")


PROFILE_DIR = Path(".runtime/whatsapp-web-profile")


COMMAND_TIMEOUT_SECONDS = 180


CHAT_READY_TIMEOUT_SECONDS = 20


class WhatsAppSendUncertain(RuntimeError):
    def __init__(self, message: str, *, evidence_path: str | None = None) -> None:
        super().__init__(message)
        self.evidence_path = evidence_path


class _AttachmentBeforeFileSelectionError(RuntimeError):
    pass


DAILY_SUMMARY_IMAGE_BATCH_SIZE = 4


PLAIN_TEXT_CONFIRMATION_TIMEOUT_SECONDS = 30


PLAIN_TEXT_CONFIRMATION_GRACE_SECONDS = 3


def _result(
    status: str,
    message: str,
    *,
    message_id: str | None = None,
    draft_mode: str | None = None,
    manual_send_required: bool = True,
    sent: bool = False,
    qr_image_data_url: str | None = None,
    delivery_phase: str | None = None,
    evidence_path: str | None = None,
    delivery_components: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = {
        "status": status,
        "message": message,
        "message_id": message_id,
        "manual_send_required": manual_send_required,
        "sent": sent,
    }
    if draft_mode is not None:
        result["draft_mode"] = draft_mode
    if qr_image_data_url is not None:
        result["qr_image_data_url"] = qr_image_data_url
    if delivery_phase is not None:
        result["delivery_phase"] = delivery_phase
    if evidence_path is not None:
        result["evidence_path"] = evidence_path
    if delivery_components is not None:
        result["delivery_components"] = dict(delivery_components)
    return result
