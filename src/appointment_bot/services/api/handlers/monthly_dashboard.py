from __future__ import annotations

import logging

from appointment_bot.services.api.monthly_dashboard_routes import monthly_dashboard_payload
from appointment_bot.services.api.routing import ApiRequest

logger = logging.getLogger("appointment_bot.services.local_api")


def get_monthly_dashboard(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    logger.warning(
        "Deprecated API accessed: GET /api/v1/monthly-summary; use /api/v2/monthly-summary"
    )
    status, payload = monthly_dashboard_payload(query)
    handler._send_json(
        status,
        payload,
        headers={
            "Deprecation": "true",
            "Sunset": "Fri, 04 Sep 2026 05:00:00 GMT",
            "Link": '</api/v2/monthly-summary>; rel="successor-version"',
        },
    )
    return
