from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import asdict, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from appointment_bot.config import load_settings
from appointment_bot.domain import public_report_dict
from appointment_bot.main import run_with_report
from appointment_bot.services.database import get_worker_state
from appointment_bot.services.queue_runner import run_queue_with_report

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class LocalApiHandler(BaseHTTPRequestHandler):
    server_version = "AppointmentBotLocalApi/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
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

        if self.path == "/status":
            if not self._is_authorized():
                self._send_json(
                    HTTPStatus.UNAUTHORIZED,
                    {"status": "unauthorized", "message": "Invalid local API token."},
                )
                return
            controller = getattr(self.server, "worker_controller", None)
            if controller is not None:
                payload = controller.status()
            else:
                settings = load_settings(require_login=False)
                payload = asdict(get_worker_state(settings))
                payload["worker_running"] = False
                payload["continuous_worker_enabled"] = settings.continuous_worker_enabled
            self._send_json(HTTPStatus.OK, payload)
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
        if self.path not in {"/pause", "/resume", "/run", "/run-queue"}:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {
                    "status": "not_found",
                    "message": "Use POST /pause, /resume, /run or /run-queue.",
                },
            )
            return

        if not self._is_authorized():
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"status": "unauthorized", "message": "Invalid local API token."},
            )
            return

        controller = getattr(self.server, "worker_controller", None)
        if self.path in {"/pause", "/resume"}:
            if controller is None:
                self._send_json(
                    HTTPStatus.CONFLICT,
                    {
                        "status": "conflict",
                        "message": "The continuous worker is not hosted by this process.",
                    },
                )
                return
            payload = controller.pause() if self.path == "/pause" else controller.resume()
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
            if self.path == "/run-queue":
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

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _is_authorized(self) -> bool:
        token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
        if not token:
            return True

        header_value = self.headers.get("Authorization", "")
        return hmac.compare_digest(header_value, f"Bearer {token}")

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


if __name__ == "__main__":
    raise SystemExit(run_local_api())
