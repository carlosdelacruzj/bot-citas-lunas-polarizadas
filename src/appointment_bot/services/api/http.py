from __future__ import annotations

import hmac
import json
import mimetypes
import os
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

MAX_JSON_BODY_BYTES = 64 * 1024


class RequestBodyError(ValueError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def require_authorized(
    handler: BaseHTTPRequestHandler,
    *,
    strict: bool = False,
) -> bool:
    if _trusted_dashboard_session(handler):
        return True
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


def _trusted_dashboard_session(handler: BaseHTTPRequestHandler) -> bool:
    expected = getattr(handler.server, "dashboard_session_token", "")
    if not expected or handler.client_address[0] not in {"127.0.0.1", "::1"}:
        return False
    cookie_header = handler.headers.get("Cookie", "")
    if not cookie_header:
        return False
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except CookieError:
        return False
    session = cookie.get("appointment_bot_dashboard")
    return session is not None and hmac.compare_digest(session.value, expected)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except ValueError as exc:
        raise RequestBodyError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length header.") from exc
    if length < 0:
        raise RequestBodyError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length header.")
    if length > MAX_JSON_BODY_BYTES:
        raise RequestBodyError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "JSON body is too large.")
    if length <= 0:
        return {}
    try:
        body = handler.rfile.read(length).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RequestBodyError(HTTPStatus.BAD_REQUEST, "JSON body must use UTF-8.") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RequestBodyError(HTTPStatus.BAD_REQUEST, "Invalid JSON body.") from exc
    if not isinstance(payload, dict):
        raise RequestBodyError(HTTPStatus.BAD_REQUEST, "JSON body must be an object.")
    return payload


def send_json(
    handler: BaseHTTPRequestHandler,
    status: HTTPStatus,
    payload: dict[str, Any],
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_png(handler: BaseHTTPRequestHandler, path: Path) -> None:
    send_image(handler, path)


def send_image(handler: BaseHTTPRequestHandler, path: Path) -> None:
    body = path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Disposition", f'inline; filename="{path.name}"')
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_download(
    handler: BaseHTTPRequestHandler,
    body: bytes,
    *,
    filename: str,
    content_type: str = "application/octet-stream",
) -> None:
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_payload(status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"status": status, "message": message}
    payload.update(extra)
    return payload
