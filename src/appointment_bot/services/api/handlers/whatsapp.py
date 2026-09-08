from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.http import error_payload, send_image, send_png
from appointment_bot.services.api.routing import ApiRequest
from appointment_bot.services.api.whatsapp_routes import (
    attachment_payload,
    followup_attachment_payload,
    payment_attachment_payload,
)


def get_attachment(request: ApiRequest) -> None:
    handler = request.transport
    attachment_message_id = request.match
    status, payload = attachment_payload(attachment_message_id)
    if isinstance(payload, dict):
        handler._send_json(status, payload)
    else:
        send_png(handler, payload)
    return


def get_payment_attachment(request: ApiRequest) -> None:
    handler = request.transport
    payment_attachment_message_id = request.match
    status, payload = payment_attachment_payload(payment_attachment_message_id)
    if isinstance(payload, dict):
        handler._send_json(status, payload)
    else:
        send_image(handler, payload)
    return


def get_followup_attachment(request: ApiRequest) -> None:
    handler = request.transport
    path = request.path
    parts = path.removeprefix("/api/v1/whatsapp-followup-messages/").split("/attachments/")
    if len(parts) != 2:
        handler._send_json(
            HTTPStatus.NOT_FOUND,
            error_payload("not_found", "Adjunto no encontrado."),
        )
        return
    message_id, suffix = parts
    try:
        step_text, attachment_text = suffix.split("/", 1)
        step_index = int(step_text)
        attachment_index = int(attachment_text)
    except ValueError:
        handler._send_json(
            HTTPStatus.NOT_FOUND,
            error_payload("not_found", "Adjunto no encontrado."),
        )
        return
    status, payload = followup_attachment_payload(
        message_id,
        step_index,
        attachment_index,
    )
    if isinstance(payload, dict):
        handler._send_json(status, payload)
    else:
        send_image(handler, payload)
    return
