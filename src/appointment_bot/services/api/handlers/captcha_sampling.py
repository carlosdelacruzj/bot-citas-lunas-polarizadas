from __future__ import annotations

from appointment_bot.services.api.captcha_sampling_routes import (
    captcha_sampling_control_payload,
    update_captcha_sampling_control_payload,
)
from appointment_bot.services.api.routing import ApiRequest


def get_captcha_sampling_control(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = captcha_sampling_control_payload()
    handler._send_json(status, payload)
    return


def post_update_captcha_sampling_control(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = update_captcha_sampling_control_payload(
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return
