from __future__ import annotations

from appointment_bot.services.api.manual_session_routes import (
    close_manual_session_payload,
    list_manual_sessions_payload,
    open_manual_session_payload,
)
from appointment_bot.services.api.routing import ApiRequest


def get_list_manual_sessions(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = list_manual_sessions_payload()
    handler._send_json(status, payload)
    return


def post_open_manual_session(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = open_manual_session_payload(
        handler._read_json(),
        server_host=str(handler.server.server_address[0]),
        client_host=str(handler.client_address[0]),
    )
    handler._send_json(status, payload)
    return


def post_close_manual_session(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = close_manual_session_payload(handler._read_json())
    handler._send_json(status, payload)
    return
