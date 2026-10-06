from __future__ import annotations

from appointment_bot.services.api.monthly_dashboard_v2_routes import monthly_dashboard_v2_payload
from appointment_bot.services.api.routing import ApiRequest


def get_monthly_dashboard_v2(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = monthly_dashboard_v2_payload(query)
    handler._send_json(status, payload)
    return
