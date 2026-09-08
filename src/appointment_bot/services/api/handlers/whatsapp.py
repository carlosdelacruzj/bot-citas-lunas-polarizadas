from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.http import error_payload, send_image, send_png
from appointment_bot.services.api.routing import ApiRequest
from appointment_bot.services.api.whatsapp_routes import (
    attachment_payload,
    followup_attachment_payload,
    mark_followup_sent_payload,
    mark_sent_payload,
    payment_attachment_payload,
    prepare_followup_payload,
    prepare_followup_test_payload,
    prepare_followup_web_payload,
    prepare_order_payload,
    prepare_test_payload,
    prepare_web_payload,
    resolve_whatsapp_review_payload,
    validate_whatsapp_session_payload,
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


def post_prepare_test(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = prepare_test_payload(handler._read_json())
    handler._send_json(status, payload)
    return


def post_prepare_followup_test(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = prepare_followup_test_payload(handler._read_json())
    handler._send_json(status, payload)
    return


def post_validate_whatsapp_session(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = validate_whatsapp_session_payload(
        server_host=str(handler.server.server_address[0]),
        client_host=str(handler.client_address[0]),
    )
    handler._send_json(status, payload)
    return


def post_prepare_order(request: ApiRequest) -> None:
    handler = request.transport
    whatsapp_order_id = request.match
    status, payload = prepare_order_payload(whatsapp_order_id, handler._read_json())
    handler._send_json(status, payload)
    return


def post_mark_sent(request: ApiRequest) -> None:
    handler = request.transport
    whatsapp_message_id = request.match
    status, payload = mark_sent_payload(whatsapp_message_id)
    handler._send_json(status, payload)
    return


def post_prepare_web(request: ApiRequest) -> None:
    handler = request.transport
    whatsapp_web_message_id = request.match
    status, payload = prepare_web_payload(
        whatsapp_web_message_id,
        payload=handler._read_json(),
        server_host=str(handler.server.server_address[0]),
        client_host=str(handler.client_address[0]),
    )
    handler._send_json(status, payload)
    return


def post_prepare_followup(request: ApiRequest) -> None:
    handler = request.transport
    whatsapp_followup_order_id = request.match
    status, payload = prepare_followup_payload(
        whatsapp_followup_order_id,
        handler._read_json(),
    )
    handler._send_json(status, payload)
    return


def post_prepare_followup_web(request: ApiRequest) -> None:
    handler = request.transport
    whatsapp_followup_web_message_id = request.match
    status, payload = prepare_followup_web_payload(
        whatsapp_followup_web_message_id,
        server_host=str(handler.server.server_address[0]),
        client_host=str(handler.client_address[0]),
    )
    handler._send_json(status, payload)
    return


def post_mark_followup_sent(request: ApiRequest) -> None:
    handler = request.transport
    whatsapp_followup_message_id = request.match
    status, payload = mark_followup_sent_payload(whatsapp_followup_message_id)
    handler._send_json(status, payload)
    return


def post_resolve_whatsapp_review(request: ApiRequest) -> None:
    handler = request.transport
    whatsapp_review_job_key = request.match
    status, payload = resolve_whatsapp_review_payload(
        whatsapp_review_job_key,
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return
