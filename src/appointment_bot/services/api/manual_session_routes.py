from __future__ import annotations

import os
from http import HTTPStatus
from typing import Any

from appointment_bot.config import load_settings
from appointment_bot.manual_session.session import open_manual_session_for_order
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.postgres_orders import get_service_order_runtime

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


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
    try:
        session_id = open_manual_session_for_order(settings, order)
    except RuntimeError as exc:
        return HTTPStatus.CONFLICT, error_payload("conflict", str(exc))
    return HTTPStatus.ACCEPTED, {
        "status": "opening",
        "session_id": session_id,
        "order_id": order.order_id,
        "message": "Manual browser session is opening locally.",
    }
