from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.http import error_payload
from appointment_bot.services.api.routing import ApiRequest
from appointment_bot.services.api.service_order_routes import (
    apply_service_order_action,
    close_service_order_payload,
    create_service_order_payload,
    get_service_order_credentials_payload,
    get_service_order_payload,
    list_service_orders_payload,
    mark_payment_paid_payload,
    record_partial_payment_payload,
    resolve_service_order_programs_payload,
    revalidate_service_order_payload,
    search_service_orders_payload,
    split_service_order_programs_payload,
    update_service_order_contact_payload,
    update_service_order_credentials_payload,
    update_service_order_priority_payload,
    update_service_order_restrictions_payload,
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


def post_create_service_order(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = create_service_order_payload(
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return


def post_search_service_orders(request: ApiRequest) -> None:
    handler = request.transport
    payload = handler._read_json()
    handler._send_json(
        HTTPStatus.OK,
        search_service_orders_payload(str(payload.get("query") or "")),
    )
    return


def post_update_service_order_contact(request: ApiRequest) -> None:
    handler = request.transport
    contact_order_id = request.match
    status, payload = update_service_order_contact_payload(
        contact_order_id,
        handler._read_json(),
    )
    handler._send_json(status, payload)
    return


def post_update_service_order_credentials(request: ApiRequest) -> None:
    handler = request.transport
    credentials_order_id = request.match
    status, payload = update_service_order_credentials_payload(
        credentials_order_id,
        handler._read_json(),
    )
    handler._send_json(status, payload)
    return


def post_update_service_order_priority(request: ApiRequest) -> None:
    handler = request.transport
    priority_order_id = request.match
    status, payload = update_service_order_priority_payload(
        priority_order_id,
        handler._read_json(),
    )
    handler._send_json(status, payload)
    return


def post_update_service_order_restrictions(request: ApiRequest) -> None:
    handler = request.transport
    restrictions_order_id = request.match
    status, payload = update_service_order_restrictions_payload(
        restrictions_order_id,
        handler._read_json(),
    )
    handler._send_json(status, payload)
    return


def post_revalidate_service_order(request: ApiRequest) -> None:
    handler = request.transport
    revalidate_order_id = request.match
    status, payload = revalidate_service_order_payload(revalidate_order_id)
    handler._send_json(status, payload)
    return


def post_mark_payment_paid(request: ApiRequest) -> None:
    handler = request.transport
    paid_order_id = request.match
    status, payload = mark_payment_paid_payload(
        paid_order_id,
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return


def post_record_partial_payment(request: ApiRequest) -> None:
    handler = request.transport
    partial_order_id = request.match
    status, payload = record_partial_payment_payload(
        partial_order_id,
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return


def post_close_service_order(request: ApiRequest) -> None:
    handler = request.transport
    close_order_id = request.match
    status, payload = close_service_order_payload(close_order_id, handler._read_json())
    handler._send_json(status, payload)
    return


def post_split_service_order_programs(request: ApiRequest) -> None:
    handler = request.transport
    split_order_id = request.match
    status, payload = split_service_order_programs_payload(
        split_order_id,
        handler._read_json(),
    )
    handler._send_json(status, payload)
    return


def post_resolve_service_order_programs(request: ApiRequest) -> None:
    handler = request.transport
    program_resolution_order_id = request.match
    status, payload = resolve_service_order_programs_payload(
        program_resolution_order_id,
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return


def post_apply_service_order_action(request: ApiRequest) -> None:
    handler = request.transport
    path = request.path
    status, payload = apply_service_order_action(path) or (
        HTTPStatus.NOT_FOUND,
        error_payload("not_found", "Unsupported service order action."),
    )
    handler._send_json(status, payload)
    return
