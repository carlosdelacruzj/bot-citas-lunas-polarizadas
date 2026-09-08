from __future__ import annotations

from appointment_bot.services.api.captcha_shadow_routes import (
    captcha_shadow_dataset_export_payload,
    captcha_shadow_events_payload,
    captcha_shadow_image_payload,
    captcha_shadow_quality_cases_payload,
    captcha_shadow_quality_payload,
    captcha_shadow_summary_payload,
)
from appointment_bot.services.api.http import send_download, send_image
from appointment_bot.services.api.routing import ApiRequest


def get_captcha_shadow_summary(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = captcha_shadow_summary_payload()
    handler._send_json(status, payload)
    return


def get_captcha_shadow_events(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = captcha_shadow_events_payload(query)
    handler._send_json(status, payload)
    return


def get_captcha_shadow_quality(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = captcha_shadow_quality_payload()
    handler._send_json(status, payload)
    return


def get_captcha_shadow_quality_cases(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = captcha_shadow_quality_cases_payload(query)
    handler._send_json(status, payload)
    return


def get_captcha_shadow_dataset_export(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = captcha_shadow_dataset_export_payload()
    if isinstance(payload, dict):
        handler._send_json(status, payload)
    else:
        send_download(
            handler,
            payload,
            filename="captcha-human-validated-dataset.zip",
            content_type="application/zip",
        )
    return


def get_captcha_shadow_image(request: ApiRequest) -> None:
    handler = request.transport
    captcha_event_id = request.match
    status, payload = captcha_shadow_image_payload(captcha_event_id)
    if isinstance(payload, dict):
        handler._send_json(status, payload)
    else:
        send_image(handler, payload)
    return
