from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.http import error_payload
from appointment_bot.services.api.routing import ApiRequest
from appointment_bot.services.api.service_order_routes import (
    get_service_order_credentials_payload,
    get_service_order_payload,
    list_service_orders_payload,
)
from appointment_bot.services.api.whatsapp_routes import (
    order_whatsapp_review_path,
    whatsapp_review_payload,
)


def get_list_service_orders(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    projection = str((query.get("projection") or ["full"])[0]).strip().lower()
    if projection not in {"full", "dashboard"}:
        handler._send_json(
            HTTPStatus.BAD_REQUEST,
            {"error": "bad_request", "message": "Unsupported service-order projection."},
        )
        return
    handler._send_json(
        HTTPStatus.OK,
        list_service_orders_payload(projection=projection),
    )
    return


def get_service_order_detail(request: ApiRequest) -> None:
    handler = request.transport
    path = request.path
    followup_review_order_id = order_whatsapp_review_path(path, "whatsapp-followup")
    if followup_review_order_id is not None:
        status, payload = whatsapp_review_payload(
            followup_review_order_id,
            job_kind="post_payment_followup",
        )
        handler._send_json(status, payload)
        return
    message_review_order_id = order_whatsapp_review_path(path, "whatsapp")
    if message_review_order_id is not None:
        status, payload = whatsapp_review_payload(
            message_review_order_id,
            job_kind="reservation_album",
        )
        handler._send_json(status, payload)
        return
    credentials_result = get_service_order_credentials_payload(path)
    if credentials_result is not None:
        status, payload = credentials_result
        handler._send_json(status, payload)
        return
    result = get_service_order_payload(path)
    if result is not None:
        status, payload = result
        handler._send_json(status, payload)
        return
    handler._send_json(
        HTTPStatus.NOT_FOUND,
        error_payload(
            "not_found",
            "Use GET /health or the /api/v1 endpoints.",
        ),
    )
