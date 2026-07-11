from __future__ import annotations

import os
from http import HTTPStatus
from typing import Any

from appointment_bot.config import load_settings
from appointment_bot.db.orders import get_service_order_runtime
from appointment_bot.manual_session.session import (
    close_manual_session,
    list_manual_sessions,
    open_manual_session_for_order,
)
from appointment_bot.services.api.http import error_payload

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def list_manual_sessions_payload() -> tuple[HTTPStatus, dict[str, Any]]:
    return HTTPStatus.OK, {"manual_sessions": list_manual_sessions()}


def open_manual_session_payload(
    payload: dict[str, Any],
    *,
    server_host: str,
    client_host: str,
) -> tuple[HTTPStatus, dict[str, Any]]:
    if os.getenv("MANUAL_SESSION_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return HTTPStatus.FORBIDDEN, error_payload(
            "configuration_error",
            "Manual sessions are disabled. Set MANUAL_SESSION_ENABLED=true locally to enable.",
        )
    if server_host not in LOOPBACK_HOSTS or client_host not in LOOPBACK_HOSTS:
        return HTTPStatus.FORBIDDEN, error_payload(
            "forbidden",
            "Manual sessions are allowed only from loopback.",
        )
    order_id = str(payload.get("order_id") or "").strip()
    if not order_id:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", "Missing order_id.")

    settings = load_settings(require_login=False)
    order = get_service_order_runtime(order_id, settings=settings)
    if order is None:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", "Service order not found.")
    session_id = open_manual_session_for_order(settings, order)
    return HTTPStatus.ACCEPTED, {
        "status": "opening",
        "session_id": session_id,
        "order_id": order.order_id,
        "message": "Manual browser session is opening locally.",
    }


def close_manual_session_payload(payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", "Missing session_id.")
    if not close_manual_session(session_id):
        return HTTPStatus.NOT_FOUND, error_payload("not_found", "Manual session not found.")
    return HTTPStatus.ACCEPTED, {
        "status": "closing",
        "session_id": session_id,
        "message": "Manual browser session close requested.",
    }
