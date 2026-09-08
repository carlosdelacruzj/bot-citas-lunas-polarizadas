from __future__ import annotations

from appointment_bot.services.api.captcha_authority_routes import captcha_authority_control_payload
from appointment_bot.services.api.routing import ApiRequest


def get_captcha_authority_control(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = captcha_authority_control_payload()
    handler._send_json(status, payload)
    return
