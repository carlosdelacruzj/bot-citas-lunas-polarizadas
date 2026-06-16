from __future__ import annotations

import logging
import os
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from appointment_bot.config import load_settings
from appointment_bot.domain import public_report_dict
from appointment_bot.main import run_with_report
from appointment_bot.services.api.client_routes import (
    apply_client_action,
    client_action,
    client_id_from_path,
    create_client,
    list_clients_payload,
    update_client_payload,
)
from appointment_bot.services.api.http import (
    error_payload,
    is_authorized,
    read_json,
    require_authorized,
    send_json,
)
from appointment_bot.services.api.run_routes import get_run_payload, list_runs_payload
from appointment_bot.services.api.worker_routes import health_payload, worker_payload
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
            healthy, payload = health_payload(controller)
            self._send_json(HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE, payload)
            return

        if path == "/status":
            if not self._require_authorized():
                return
            self._send_json(
                HTTPStatus.OK,
                worker_payload(getattr(self.server, "worker_controller", None)),
            )
            return

        if path == "/api/v1/worker":
            if not self._require_authorized(strict=True):
                return
            self._send_json(
                HTTPStatus.OK,
                worker_payload(getattr(self.server, "worker_controller", None)),
            )
            return

        if path == "/api/v1/clients":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, list_clients_payload())
            return

        if path == "/api/v1/runs":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, list_runs_payload(query))
            return

        if path.startswith("/api/v1/runs/"):
            if not self._require_authorized(strict=True):
                return
            status, payload = get_run_payload(path)
            self._send_json(status, payload)
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            error_payload(
                "not_found",
                "Use GET /health, GET /status, POST /pause, POST /resume, "
                "POST /run or POST /run-queue.",
            ),
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/v1/clients":
            if not self._require_authorized(strict=True):
                return
            status, payload = create_client(self._read_json())
            self._send_json(status, payload)
            return

        if client_action(path) is not None:
            if not self._require_authorized(strict=True):
                return
            client_action_result = apply_client_action(path)
            if client_action_result is None:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    error_payload("not_found", "Unsupported client action."),
                )
                return
            status, payload = client_action_result
            self._send_json(status, payload)
            return

        if path not in {"/pause", "/resume", "/run", "/run-queue"}:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                error_payload("not_found", "Use POST /pause, /resume, /run or /run-queue."),
            )
            return

        if not self._require_authorized():
            return

        controller = getattr(self.server, "worker_controller", None)
        if path in {"/pause", "/resume"}:
            if controller is None:
                self._send_json(
                    HTTPStatus.CONFLICT,
                    error_payload(
                        "conflict",
                        "The continuous worker is not hosted by this process.",
                    ),
                )
                return
            payload = controller.pause() if path == "/pause" else controller.resume()
            self._send_json(HTTPStatus.OK, payload)
            return

        if controller is not None and controller.is_starting_or_running:
            self._send_json(
                HTTPStatus.CONFLICT,
                error_payload(
                    "conflict",
                    "Manual runs are disabled while the continuous worker is active.",
                ),
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
                error_payload(
                    "error",
                    "Local API request failed.",
                    exit_code=1,
                    details={"error_type": type(exc).__name__},
                ),
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
                error_payload("not_found", "Use PATCH /api/v1/clients/{client_id}."),
            )
            return
        if not self._require_authorized(strict=True):
            return
        status, payload = update_client_payload(client_id_from_path(path), self._read_json())
        self._send_json(status, payload)

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _is_authorized(self) -> bool:
        return is_authorized(self.headers)

    def _require_authorized(self, *, strict: bool = False) -> bool:
        return require_authorized(self, strict=strict)

    def _read_json(self) -> dict[str, Any]:
        return read_json(self)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        send_json(self, status, payload)


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


if __name__ == "__main__":
    raise SystemExit(run_local_api())
