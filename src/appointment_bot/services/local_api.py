from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from appointment_bot.services.api.get_routes import GET_ROUTES
from appointment_bot.services.api.http import (
    RequestBodyError,
    authenticated_actor,
    error_payload,
    read_json,
    require_authorized,
    send_json,
)
from appointment_bot.services.api.post_routes import POST_ROUTES
from appointment_bot.services.api.put_routes import PUT_ROUTES
from appointment_bot.services.api.routing import ApiRequest, Route, dispatch

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class LocalApiHandler(BaseHTTPRequestHandler):
    server_version = "AppointmentBotLocalApi/0.1"

    def do_GET(self) -> None:
        self._dispatch(GET_ROUTES, "Use GET /health or the /api/v1 endpoints.", parse_query=True)

    def do_POST(self) -> None:
        try:
            self._dispatch(POST_ROUTES, "Use the /api/v1/worker control endpoints.")
        except RequestBodyError as exc:
            self._send_json(
                exc.status,
                error_payload("bad_request", str(exc)),
            )

    def do_PUT(self) -> None:
        try:
            self._dispatch(PUT_ROUTES, "Use los endpoints de plantillas de WhatsApp.")
        except RequestBodyError as exc:
            self._send_json(
                exc.status,
                error_payload("bad_request", str(exc)),
            )

    def _dispatch(
        self,
        routes: Sequence[Route],
        not_found_message: str,
        *,
        parse_query: bool = False,
    ) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query) if parse_query else {}
        request = ApiRequest(self, parsed.path, query)
        if not dispatch(request, routes):
            self._send_json(
                HTTPStatus.NOT_FOUND,
                error_payload("not_found", not_found_message),
            )

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _require_authorized(self, *, strict: bool = False) -> bool:
        return require_authorized(self, strict=strict)

    def _authenticated_actor(self) -> str:
        return authenticated_actor(self)

    def _read_json(self) -> dict[str, Any]:
        return read_json(self)

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        send_json(self, status, payload, headers=headers)


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
