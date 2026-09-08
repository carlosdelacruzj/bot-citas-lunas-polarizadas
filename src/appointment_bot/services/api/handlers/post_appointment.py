from __future__ import annotations

from appointment_bot.services.api.post_appointment_routes import post_appointment_followups_payload
from appointment_bot.services.api.routing import ApiRequest


def get_post_appointment_followups(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = post_appointment_followups_payload(query)
    handler._send_json(status, payload)
    return
