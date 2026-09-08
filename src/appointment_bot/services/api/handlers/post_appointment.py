from __future__ import annotations

from appointment_bot.services.api.post_appointment_routes import (
    post_appointment_followups_payload,
    review_post_appointment_payload,
)
from appointment_bot.services.api.routing import ApiRequest


def get_post_appointment_followups(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = post_appointment_followups_payload(query)
    handler._send_json(status, payload)
    return


def post_review_post_appointment(request: ApiRequest) -> None:
    handler = request.transport
    post_appointment_order_id = request.match
    status, payload = review_post_appointment_payload(post_appointment_order_id)
    handler._send_json(status, payload)
    return
