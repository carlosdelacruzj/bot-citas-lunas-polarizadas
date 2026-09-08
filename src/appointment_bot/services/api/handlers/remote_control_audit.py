from __future__ import annotations

import logging
from http import HTTPStatus

from appointment_bot.db.remote_control_audit import (
    VALID_AUDIT_STATUSES,
    record_remote_control_audit,
)
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.api.routing import ApiRequest

logger = logging.getLogger(__name__)


def post_remote_control_audit(request: ApiRequest) -> None:
    handler = request.transport
    payload = handler._read_json()
    fields = ("action", "status", "target_type", "target_id", "operation_id", "detail")
    for field in fields:
        value = payload.get(field)
        required = field in {"action", "status"}
        if (required and (not isinstance(value, str) or not value.strip())) or (
            value is not None and not isinstance(value, str)
        ):
            handler._send_json(
                HTTPStatus.BAD_REQUEST, error_payload("bad_request", f"Invalid audit {field}.")
            )
            return
    if payload["status"].strip().lower() not in VALID_AUDIT_STATUSES:
        handler._send_json(
            HTTPStatus.BAD_REQUEST, error_payload("bad_request", "Invalid audit status.")
        )
        return
    try:
        audit_id = record_remote_control_audit(
            actor=handler._authenticated_actor(),
            **{field: payload.get(field) for field in fields},
        )
    except Exception:
        logger.warning("Could not persist remote-control audit received by Admin API")
        handler._send_json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            error_payload("audit_unavailable", "Audit persistence is unavailable."),
        )
        return
    handler._send_json(HTTPStatus.CREATED, {"audit_id": audit_id, "status": "recorded"})
