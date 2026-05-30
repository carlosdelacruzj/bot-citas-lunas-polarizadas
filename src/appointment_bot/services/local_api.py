from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from appointment_bot.main import run_with_report

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class LocalApiHandler(BaseHTTPRequestHandler):
    server_version = "AppointmentBotLocalApi/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "message": "Appointment bot local API is running.",
                },
            )
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            {"status": "not_found", "message": "Use GET /health or POST /run."},
        )

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "not_found", "message": "Use POST /run."},
            )
            return

        if not self._is_authorized():
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"status": "unauthorized", "message": "Invalid local API token."},
            )
            return

        report = run_with_report()
        http_status = HTTPStatus.OK if report.exit_code == 0 else HTTPStatus.INTERNAL_SERVER_ERROR
        self._send_json(http_status, asdict(report))

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _is_authorized(self) -> bool:
        token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
        if not token:
            return True

        header_value = self.headers.get("Authorization", "")
        return header_value == f"Bearer {token}"

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_local_api() -> int:
    host = os.getenv("APPOINTMENT_BOT_API_HOST", DEFAULT_HOST)
    port = int(os.getenv("APPOINTMENT_BOT_API_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer((host, port), LocalApiHandler)
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
