from __future__ import annotations

import hmac
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any


def is_authorized(headers) -> bool:
    token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
    if not token:
        return True
    header_value = headers.get("Authorization", "")
    return hmac.compare_digest(header_value, f"Bearer {token}")


def require_authorized(
    handler: BaseHTTPRequestHandler,
    *,
    strict: bool = False,
) -> bool:
    token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
    if not token:
        if strict:
            send_json(
                handler,
                HTTPStatus.SERVICE_UNAVAILABLE,
                error_payload(
                    "configuration_error",
                    "APPOINTMENT_BOT_API_TOKEN is required for this endpoint.",
                ),
            )
            return False
        return True

    header_value = handler.headers.get("Authorization", "")
    if hmac.compare_digest(header_value, f"Bearer {token}"):
        return True
    send_json(
        handler,
        HTTPStatus.UNAUTHORIZED,
        error_payload("unauthorized", "Invalid local API token."),
    )
    return False


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    body = handler.rfile.read(length).decode("utf-8")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def send_json(
    handler: BaseHTTPRequestHandler,
    status: HTTPStatus,
    payload: dict[str, Any],
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_payload(status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"status": status, "message": message}
    payload.update(extra)
    return payload
