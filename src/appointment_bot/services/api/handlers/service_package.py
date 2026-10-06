from __future__ import annotations

from appointment_bot.services.api.routing import ApiRequest
from appointment_bot.services.api.service_package_routes import service_packages_payload


def get_service_packages(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = service_packages_payload()
    handler._send_json(status, payload)
    return
