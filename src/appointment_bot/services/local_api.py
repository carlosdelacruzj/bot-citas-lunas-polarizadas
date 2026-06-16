from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import asdict, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from appointment_bot.config import load_settings
from appointment_bot.domain import public_report_dict
from appointment_bot.main import run_with_report
from appointment_bot.services.database import (
    add_client,
    get_run,
    get_worker_state,
    list_client_summaries,
    list_runs,
    mark_client_done,
    set_client_active,
    update_client,
)
from appointment_bot.services.queue_runner import run_queue_with_report

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class LocalApiHandler(BaseHTTPRequestHandler):
    server_version = "AppointmentBotLocalApi/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/health":
            controller = getattr(self.server, "worker_controller", None)
            if controller is None:
                healthy, reason = True, "api_only"
                worker_running = False
            else:
                healthy, reason = controller.health()
                worker_running = controller.is_running
            self._send_json(
                HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "status": "ok" if healthy else "degraded",
                    "message": (
                        "Appointment bot local API is running."
                        if healthy
                        else "Appointment bot API is running, but the worker is stopped."
                    ),
                    "worker_running": worker_running,
                    "reason": reason,
                },
            )
            return

        if path == "/status":
            if not self._require_authorized():
                return
            self._send_json(HTTPStatus.OK, self._worker_payload())
            return

        if path == "/api/v1/worker":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, self._worker_payload())
            return

        if path == "/api/v1/clients":
            if not self._require_authorized(strict=True):
                return
            self._send_json(
                HTTPStatus.OK,
                {"clients": [asdict(client) for client in list_client_summaries()]},
            )
            return

        if path == "/api/v1/runs":
            if not self._require_authorized(strict=True):
                return
            limit = _query_int(query, "limit", default=50, minimum=1, maximum=200)
            offset = _query_int(query, "offset", default=0, minimum=0, maximum=10_000)
            client_id = _query_text(query, "client_id")
            status = _query_text(query, "status")
            self._send_json(
                HTTPStatus.OK,
                {
                    "runs": [
                        asdict(run)
                        for run in list_runs(
                            limit=limit,
                            offset=offset,
                            client_id=client_id,
                            status=status,
                        )
                    ],
                    "limit": limit,
                    "offset": offset,
                },
            )
            return

        if path.startswith("/api/v1/runs/"):
            if not self._require_authorized(strict=True):
                return
            run_id = unquote(path.removeprefix("/api/v1/runs/")).strip()
            run = get_run(run_id) if run_id else None
            if run is None:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"status": "not_found", "message": "Run not found."},
                )
                return
            self._send_json(HTTPStatus.OK, asdict(run))
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            {
                "status": "not_found",
                "message": (
                    "Use GET /health, GET /status, POST /pause, POST /resume, "
                    "POST /run or POST /run-queue."
                ),
            },
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/v1/clients":
            if not self._require_authorized(strict=True):
                return
            payload = self._read_json()
            required = ("client_id", "name", "username", "password", "priority")
            missing = [field for field in required if payload.get(field) in {None, ""}]
            if missing:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "bad_request", "message": f"Missing fields: {', '.join(missing)}"},
                )
                return
            try:
                add_client(
                    str(payload["client_id"]).strip(),
                    str(payload["name"]).strip(),
                    str(payload["username"]).strip(),
                    str(payload["password"]),
                    int(payload["priority"]),
                )
            except (TypeError, ValueError) as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "bad_request", "message": str(exc)},
                )
                return
            self._send_json(HTTPStatus.CREATED, {"status": "created"})
            return

        client_action = _client_action(path)
        if client_action is not None:
            if not self._require_authorized(strict=True):
                return
            client_id, action = client_action
            try:
                if action == "pause":
                    set_client_active(client_id, False)
                elif action == "activate":
                    set_client_active(client_id, True)
                elif action == "done":
                    mark_client_done(client_id, status="completed")
                else:
                    raise ValueError(f"Unsupported client action: {action}")
            except ValueError as exc:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"status": "not_found", "message": str(exc)},
                )
                return
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return

        if path not in {"/pause", "/resume", "/run", "/run-queue"}:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {
                    "status": "not_found",
                    "message": "Use POST /pause, /resume, /run or /run-queue.",
                },
            )
            return

        if not self._require_authorized():
            return

        controller = getattr(self.server, "worker_controller", None)
        if path in {"/pause", "/resume"}:
            if controller is None:
                self._send_json(
                    HTTPStatus.CONFLICT,
                    {
                        "status": "conflict",
                        "message": "The continuous worker is not hosted by this process.",
                    },
                )
                return
            payload = controller.pause() if path == "/pause" else controller.resume()
            self._send_json(HTTPStatus.OK, payload)
            return

        if controller is not None and controller.is_starting_or_running:
            self._send_json(
                HTTPStatus.CONFLICT,
                {
                    "status": "conflict",
                    "message": ("Manual runs are disabled while the continuous worker is active."),
                },
            )
            return

        try:
            if path == "/run-queue":
                report = run_queue_with_report()
            else:
                report = run_with_report(
                    replace(load_settings(), auto_reserve=False),
                )
        except Exception as exc:
            logger.exception("Local API request failed")
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "status": "error",
                    "message": "Local API request failed.",
                    "exit_code": 1,
                    "details": {"error_type": type(exc).__name__},
                },
            )
            return

        http_status = HTTPStatus.OK if report.exit_code == 0 else HTTPStatus.INTERNAL_SERVER_ERROR
        self._send_json(http_status, public_report_dict(report))

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/v1/clients/"):
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "not_found", "message": "Use PATCH /api/v1/clients/{client_id}."},
            )
            return
        if not self._require_authorized(strict=True):
            return
        client_id = unquote(path.removeprefix("/api/v1/clients/")).strip()
        payload = self._read_json()
        allowed = {"name", "username", "password", "priority"}
        invalid = sorted(set(payload) - allowed)
        if invalid:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"status": "bad_request", "message": f"Invalid fields: {', '.join(invalid)}"},
            )
            return
        try:
            update_client(
                client_id,
                name=_optional_text(payload, "name"),
                username=_optional_text(payload, "username"),
                password=_optional_text(payload, "password"),
                priority=int(payload["priority"]) if "priority" in payload else None,
            )
        except ValueError as exc:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "not_found", "message": str(exc)},
            )
            return
        self._send_json(HTTPStatus.OK, {"status": "ok"})

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _is_authorized(self) -> bool:
        token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
        if not token:
            return True

        header_value = self.headers.get("Authorization", "")
        return hmac.compare_digest(header_value, f"Bearer {token}")

    def _require_authorized(self, *, strict: bool = False) -> bool:
        token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
        if not token:
            if strict:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "status": "configuration_error",
                        "message": "APPOINTMENT_BOT_API_TOKEN is required for this endpoint.",
                    },
                )
                return False
            return True

        header_value = self.headers.get("Authorization", "")
        if hmac.compare_digest(header_value, f"Bearer {token}"):
            return True
        self._send_json(
            HTTPStatus.UNAUTHORIZED,
            {"status": "unauthorized", "message": "Invalid local API token."},
        )
        return False

    def _worker_payload(self) -> dict[str, Any]:
        controller = getattr(self.server, "worker_controller", None)
        if controller is not None:
            return controller.status()
        settings = load_settings(require_login=False)
        payload = asdict(get_worker_state(settings))
        payload["worker_running"] = False
        payload["continuous_worker_enabled"] = settings.continuous_worker_enabled
        return payload

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_local_api_server(
    *,
    worker_controller: Any | None = None,
) -> ThreadingHTTPServer:
    host = os.getenv("APPOINTMENT_BOT_API_HOST", DEFAULT_HOST)
    if (
        host not in {"127.0.0.1", "localhost", "::1"}
        and not os.getenv(
            "APPOINTMENT_BOT_API_TOKEN",
            "",
        ).strip()
    ):
        raise ValueError(
            "APPOINTMENT_BOT_API_TOKEN is required when the local API binds "
            "outside the loopback interface."
        )
    port = int(os.getenv("APPOINTMENT_BOT_API_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer((host, port), LocalApiHandler)
    server.worker_controller = worker_controller
    return server


def run_local_api() -> int:
    server = create_local_api_server()
    host, port = server.server_address[:2]
    print(f"Appointment bot local API listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping appointment bot local API")
    finally:
        server.server_close()
    return 0


def _query_int(
    query: dict[str, list[str]],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = query.get(name, [str(default)])[0]
    try:
        value = int(raw)
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def _query_text(query: dict[str, list[str]], name: str) -> str | None:
    value = query.get(name, [""])[0].strip()
    return value or None


def _optional_text(payload: dict[str, Any], name: str) -> str | None:
    if name not in payload:
        return None
    return str(payload[name])


def _client_action(path: str) -> tuple[str, str] | None:
    prefix = "/api/v1/clients/"
    if not path.startswith(prefix):
        return None
    parts = [unquote(part) for part in path.removeprefix(prefix).split("/") if part]
    if len(parts) != 2:
        return None
    client_id, action = parts
    if action not in {"pause", "activate", "done"}:
        return None
    return client_id, action


if __name__ == "__main__":
    raise SystemExit(run_local_api())
