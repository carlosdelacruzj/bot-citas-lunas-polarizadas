from __future__ import annotations

import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from appointment_bot.services.api.http import (
    RequestBodyError,
    error_payload,
    read_json,
    require_authorized,
    send_json,
)
from appointment_bot.services.api.manual_session_routes import (
    close_manual_session_payload,
    list_manual_sessions_payload,
    open_manual_session_payload,
)
from appointment_bot.services.api.run_routes import get_run_payload, list_runs_payload
from appointment_bot.services.api.service_order_routes import (
    apply_service_order_action,
    close_service_order_payload,
    create_service_order_payload,
    list_service_orders_payload,
    mark_payment_paid_payload,
    payment_paid_path,
    service_order_action,
    service_order_close_path,
    service_order_contact_path,
    service_order_split_programs_path,
    split_service_order_programs_payload,
    update_service_order_contact_payload,
)
from appointment_bot.services.api.worker_routes import (
    enqueue_worker_command_payload,
    health_payload,
    list_worker_commands_payload,
    worker_payload,
)

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

        if path == "/api/v1/worker":
            if not self._require_authorized(strict=True):
                return
            self._send_json(
                HTTPStatus.OK,
                worker_payload(getattr(self.server, "worker_controller", None)),
            )
            return

        if path == "/api/v1/worker/commands":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, list_worker_commands_payload(query))
            return

        if path == "/api/v1/manual-sessions":
            if not self._require_authorized(strict=True):
                return
            status, payload = list_manual_sessions_payload()
            self._send_json(status, payload)
            return

        if path == "/api/v1/service-orders":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, list_service_orders_payload())
            return

        if path == "/api/v1/runs":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, list_runs_payload(query))
            return

        if path.startswith("/api/v1/runs/"):
            if not self._require_authorized(strict=True):
                return
            status, payload = get_run_payload(path, query)
            self._send_json(status, payload)
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            error_payload(
                "not_found",
                "Use GET /health or the /api/v1 endpoints.",
            ),
        )

    def do_POST(self) -> None:
        try:
            self._handle_post()
        except RequestBodyError as exc:
            self._send_json(
                exc.status,
                error_payload("bad_request", str(exc)),
            )

    def _handle_post(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/v1/service-orders":
            if not self._require_authorized(strict=True):
                return
            status, payload = create_service_order_payload(self._read_json())
            self._send_json(status, payload)
            return

        contact_order_id = service_order_contact_path(path)
        if contact_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = update_service_order_contact_payload(
                contact_order_id,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        paid_order_id = payment_paid_path(path)
        if paid_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = mark_payment_paid_payload(paid_order_id, self._read_json())
            self._send_json(status, payload)
            return

        close_order_id = service_order_close_path(path)
        if close_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = close_service_order_payload(close_order_id, self._read_json())
            self._send_json(status, payload)
            return

        split_order_id = service_order_split_programs_path(path)
        if split_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = split_service_order_programs_payload(
                split_order_id,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        if service_order_action(path) is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = apply_service_order_action(path) or (
                HTTPStatus.NOT_FOUND,
                error_payload("not_found", "Unsupported service order action."),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/worker/restart":
            if not self._require_authorized(strict=True):
                return
            controller = getattr(self.server, "worker_controller", None)
            restart_callback = getattr(self.server, "restart_callback", None)
            if controller is None or restart_callback is None:
                status, payload = enqueue_worker_command_payload("restart")
                self._send_json(status, payload)
                return
            controller.prepare_restart()
            self._send_json(
                HTTPStatus.ACCEPTED,
                {"status": "restarting", "message": "Controlled restart requested."},
            )
            restart_callback()
            return

        if path == "/api/v1/manual-session/open":
            if not self._require_authorized(strict=True):
                return
            status, payload = open_manual_session_payload(
                self._read_json(),
                server_host=str(self.server.server_address[0]),
                client_host=str(self.client_address[0]),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/manual-session/close":
            if not self._require_authorized(strict=True):
                return
            status, payload = close_manual_session_payload(self._read_json())
            self._send_json(status, payload)
            return

        if path not in {"/api/v1/worker/pause", "/api/v1/worker/resume"}:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                error_payload("not_found", "Use the /api/v1/worker control endpoints."),
            )
            return

        if not self._require_authorized(strict=True):
            return

        controller = getattr(self.server, "worker_controller", None)
        if controller is None:
            command = "pause" if path.endswith("/pause") else "resume"
            status, payload = enqueue_worker_command_payload(command)
            self._send_json(status, payload)
            return
        payload = (
            controller.pause() if path.endswith("/pause") else controller.resume()
        )
        self._send_json(HTTPStatus.OK, payload)

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _require_authorized(self, *, strict: bool = False) -> bool:
        return require_authorized(self, strict=strict)

    def _read_json(self) -> dict[str, Any]:
        return read_json(self)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        send_json(self, status, payload)


def create_local_api_server(
    *,
    worker_controller: Any | None = None,
    restart_callback: Any | None = None,
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
    server.restart_callback = restart_callback
    return server
