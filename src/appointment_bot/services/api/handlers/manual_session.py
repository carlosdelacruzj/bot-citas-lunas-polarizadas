from __future__ import annotations

from appointment_bot.services.api.manual_session_routes import list_manual_sessions_payload
from appointment_bot.services.api.routing import ApiRequest


def get_list_manual_sessions(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = list_manual_sessions_payload()
    handler._send_json(status, payload)
    return
