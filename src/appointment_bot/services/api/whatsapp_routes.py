from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from appointment_bot.browser.whatsapp_web import (
    prepare_whatsapp_web_album,
    prepare_whatsapp_web_documents,
    prepare_whatsapp_web_draft,
    validate_whatsapp_web_session,
)
from appointment_bot.db.remote_control_audit import record_remote_control_audit
from appointment_bot.db.whatsapp_automation import (
    get_order_whatsapp_review,
    resolve_whatsapp_automation_review,
)
from appointment_bot.db.whatsapp_followup_messages import (
    get_followup_attachment,
    get_followup_message,
    get_followup_web_draft,
    mark_followup_message_sent,
    prepare_post_payment_whatsapp_message,
    prepare_test_post_payment_whatsapp_message,
)
from appointment_bot.db.whatsapp_messages import (
    get_whatsapp_attachment,
    get_whatsapp_payment_attachment,
    get_whatsapp_web_draft,
    mark_whatsapp_message_sent,
    prepare_order_whatsapp_message,
    prepare_test_whatsapp_message,
)
from appointment_bot.services.api.http import error_payload


def prepare_test_payload(payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
    recipient = str(payload.get("recipient_phone") or "").strip()
    if not recipient:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            "Missing recipient_phone.",
            field_errors={"recipient_phone": "Ingresa tu numero de WhatsApp."},
        )
    try:
        result = prepare_test_whatsapp_message(recipient)
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    return HTTPStatus.CREATED, result


def prepare_followup_test_payload(payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
    recipient = str(payload.get("recipient_phone") or "").strip()
    if not recipient:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            "Missing recipient_phone.",
            field_errors={"recipient_phone": "Ingresa tu numero de WhatsApp."},
        )
    try:
        result = prepare_test_post_payment_whatsapp_message(recipient)
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    return HTTPStatus.CREATED, result


def prepare_order_payload(
    order_id: str,
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    allow_resend = payload.get("allow_resend") is True
    try:
        result = prepare_order_whatsapp_message(order_id, allow_resend=allow_resend)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            return HTTPStatus.NOT_FOUND, error_payload("not_found", message)
        if "reenvio" in message.casefold():
            return HTTPStatus.CONFLICT, error_payload("conflict", message)
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", message)
    return HTTPStatus.CREATED, result


def mark_sent_payload(message_id: str) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        return HTTPStatus.OK, mark_whatsapp_message_sent(message_id)
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))


def prepare_followup_payload(
    order_id: str,
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    allow_resend = payload.get("allow_resend") is True
    try:
        result = prepare_post_payment_whatsapp_message(order_id, allow_resend=allow_resend)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            return HTTPStatus.NOT_FOUND, error_payload("not_found", message)
        if "reenvio" in message.casefold():
            return HTTPStatus.CONFLICT, error_payload("conflict", message)
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", message)
    return HTTPStatus.CREATED, result


def mark_followup_sent_payload(message_id: str) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        return HTTPStatus.OK, mark_followup_message_sent(message_id)
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))


def whatsapp_review_payload(
    order_id: str,
    *,
    job_kind: Literal["reservation_album", "post_payment_followup"],
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        job = get_order_whatsapp_review(order_id, job_kind)
        message = (
            get_followup_message(str(job["message_id"]))
            if job_kind == "post_payment_followup" and job.get("message_id")
            else None
        )
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))
    return HTTPStatus.OK, {"job": job, "message": message}


def resolve_whatsapp_review_payload(
    job_key: str,
    payload: dict[str, Any],
    *,
    requested_by: str | None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    actor = requested_by or "system"
    try:
        result = resolve_whatsapp_automation_review(
            job_key,
            resolution=str(payload.get("resolution") or ""),
            note=str(payload.get("note") or "") or None,
            reviewed_by=actor,
        )
    except ValueError as exc:
        message = str(exc)
        status = HTTPStatus.CONFLICT if "already" in message.casefold() else HTTPStatus.BAD_REQUEST
        return status, error_payload("conflict" if status == 409 else "bad_request", message)
    record_remote_control_audit(
        actor=actor,
        action="resolve_whatsapp_review",
        status="applied",
        target_type="whatsapp_job",
        target_id=job_key,
        detail=f"resolution={result['resolution']}; order_id={result['order_id']}",
    )
    return HTTPStatus.OK, result


def attachment_payload(message_id: str) -> tuple[HTTPStatus, Path | dict[str, Any]]:
    try:
        return HTTPStatus.OK, get_whatsapp_attachment(message_id)
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))


def payment_attachment_payload(
    message_id: str,
) -> tuple[HTTPStatus, Path | dict[str, Any]]:
    try:
        return HTTPStatus.OK, get_whatsapp_payment_attachment(message_id)
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))


def followup_attachment_payload(
    message_id: str,
    step_index: int,
    attachment_index: int,
) -> tuple[HTTPStatus, Path | dict[str, Any]]:
    try:
        return HTTPStatus.OK, get_followup_attachment(message_id, step_index, attachment_index)
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))


def prepare_web_payload(
    message_id: str,
    *,
    payload: dict[str, Any],
    server_host: str,
    client_host: str,
) -> tuple[HTTPStatus, dict[str, Any]]:
    if server_host not in {"127.0.0.1", "localhost", "::1"} or client_host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        return HTTPStatus.FORBIDDEN, error_payload(
            "forbidden",
            "La preparacion de WhatsApp Web solo esta disponible desde esta computadora.",
        )
    draft_kind = str(payload.get("draft_kind") or "confirmation").strip()
    auto_send = payload.get("auto_send") is True
    try:
        if draft_kind == "album":
            confirmation = get_whatsapp_web_draft(
                message_id,
                draft_kind="confirmation",
            )
            payment = get_whatsapp_web_draft(message_id, draft_kind="payment")
        else:
            if auto_send:
                return HTTPStatus.BAD_REQUEST, error_payload(
                    "bad_request",
                    "El envio automatico solo esta disponible para el album.",
                )
            draft = get_whatsapp_web_draft(message_id, draft_kind=draft_kind)
    except ValueError as exc:
        message = str(exc)
        status = (
            HTTPStatus.NOT_FOUND
            if "not found" in message.casefold()
            else HTTPStatus.BAD_REQUEST
        )
        return status, error_payload("not_found" if status == 404 else "bad_request", message)
    result = (
        prepare_whatsapp_web_album(confirmation, payment, auto_send=auto_send)
        if draft_kind == "album"
        else prepare_whatsapp_web_draft(draft)
    )
    if result.get("sent"):
        sent_payload = mark_whatsapp_message_sent(message_id)
        result = {
            **result,
            "status": "sent",
            "sent_at": sent_payload.get("sent_at"),
        }
    status = (
        HTTPStatus.SERVICE_UNAVAILABLE
        if result["status"] == "web_unavailable"
        else HTTPStatus.OK
    )
    return status, result


def prepare_followup_web_payload(
    message_id: str,
    *,
    server_host: str,
    client_host: str,
) -> tuple[HTTPStatus, dict[str, Any]]:
    if server_host not in {"127.0.0.1", "localhost", "::1"} or client_host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        return HTTPStatus.FORBIDDEN, error_payload(
            "forbidden",
            "La preparacion de WhatsApp Web solo esta disponible desde esta computadora.",
        )
    try:
        draft = get_followup_web_draft(message_id)
    except ValueError as exc:
        message = str(exc)
        status = (
            HTTPStatus.NOT_FOUND
            if "not found" in message.casefold()
            else HTTPStatus.BAD_REQUEST
        )
        return status, error_payload("not_found" if status == 404 else "bad_request", message)
    result = prepare_whatsapp_web_documents(draft)
    if result.get("sent"):
        sent_payload = mark_followup_message_sent(message_id)
        result = {
            **result,
            "status": "sent",
            "sent_at": sent_payload.get("sent_at"),
        }
    status = (
        HTTPStatus.SERVICE_UNAVAILABLE
        if result["status"] == "web_unavailable"
        else HTTPStatus.OK
    )
    return status, result


def validate_whatsapp_session_payload(
    *,
    server_host: str,
    client_host: str,
) -> tuple[HTTPStatus, dict[str, Any]]:
    if server_host not in {"127.0.0.1", "localhost", "::1"} or client_host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        return HTTPStatus.FORBIDDEN, error_payload(
            "forbidden",
            "La validacion de WhatsApp Web solo esta disponible desde esta computadora.",
        )
    result = validate_whatsapp_web_session()
    status = (
        HTTPStatus.SERVICE_UNAVAILABLE
        if result["status"] == "web_unavailable"
        else HTTPStatus.OK
    )
    return status, result


def order_prepare_path(path: str) -> str | None:
    prefix = "/api/v1/service-orders/"
    suffix = "/whatsapp/prepare"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    return unquote(path.removeprefix(prefix).removesuffix(suffix).strip("/"))


def order_followup_prepare_path(path: str) -> str | None:
    prefix = "/api/v1/service-orders/"
    suffix = "/whatsapp-followup/prepare"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    return unquote(path.removeprefix(prefix).removesuffix(suffix).strip("/"))


def order_whatsapp_review_path(path: str, kind: str) -> str | None:
    prefix = "/api/v1/service-orders/"
    suffix = f"/{kind}/review"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    return unquote(path.removeprefix(prefix).removesuffix(suffix).strip("/"))


def whatsapp_message_path(path: str, action: str) -> str | None:
    prefix = "/api/v1/whatsapp-messages/"
    suffix = f"/{action}"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    return unquote(path.removeprefix(prefix).removesuffix(suffix).strip("/"))


def whatsapp_followup_message_path(path: str, action: str) -> str | None:
    prefix = "/api/v1/whatsapp-followup-messages/"
    suffix = f"/{action}"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    return unquote(path.removeprefix(prefix).removesuffix(suffix).strip("/"))


def whatsapp_review_job_path(path: str) -> str | None:
    prefix = "/api/v1/whatsapp-automation-jobs/"
    suffix = "/resolve"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    return unquote(path.removeprefix(prefix).removesuffix(suffix).strip("/"))


__all__ = [
    "attachment_payload",
    "followup_attachment_payload",
    "mark_followup_sent_payload",
    "payment_attachment_payload",
    "mark_sent_payload",
    "order_followup_prepare_path",
    "order_whatsapp_review_path",
    "order_prepare_path",
    "prepare_followup_test_payload",
    "prepare_followup_payload",
    "prepare_followup_web_payload",
    "prepare_web_payload",
    "prepare_order_payload",
    "prepare_test_payload",
    "validate_whatsapp_session_payload",
    "resolve_whatsapp_review_payload",
    "whatsapp_followup_message_path",
    "whatsapp_message_path",
    "whatsapp_review_job_path",
    "whatsapp_review_payload",
]
