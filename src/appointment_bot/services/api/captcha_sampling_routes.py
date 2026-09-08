from __future__ import annotations

import re
from http import HTTPStatus
from typing import Any

from appointment_bot.db.captcha_sampling_control import (
    CaptchaSamplingControl,
    get_captcha_sampling_control,
    update_captcha_sampling_control,
)
from appointment_bot.services.api.http import error_payload


def captcha_sampling_control_payload() -> tuple[HTTPStatus, dict[str, Any]]:
    return HTTPStatus.OK, _public_payload(get_captcha_sampling_control())


def update_captcha_sampling_control_payload(
    body: dict[str, Any],
    *,
    requested_by: str | None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    enabled = body.get("enabled")
    sample_limit = body.get("sample_limit")
    field_errors: dict[str, str] = {}
    if not isinstance(enabled, bool):
        field_errors["enabled"] = "Debe ser verdadero o falso."
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int):
        field_errors["sample_limit"] = "Debe ser un numero entero entre 2 y 50."
    elif not 2 <= sample_limit <= 50:
        field_errors["sample_limit"] = "Debe estar entre 2 y 50."
    if field_errors:
        payload = error_payload("bad_request", "Revisa la configuracion de muestreo.")
        payload["field_errors"] = field_errors
        return HTTPStatus.BAD_REQUEST, payload

    control = update_captcha_sampling_control(
        enabled=enabled,
        sample_limit=sample_limit,
        updated_by=_requested_by(requested_by),
    )
    return HTTPStatus.OK, _public_payload(control)


def _public_payload(control: CaptchaSamplingControl) -> dict[str, Any]:
    return {
        "enabled": control.enabled,
        "sample_limit": control.sample_limit,
        "effective_sample_limit": control.effective_sample_limit,
        "estimated_extra_seconds": control.estimated_extra_seconds,
        "applies_from": "next_captcha_batch",
        "rapid_mode_effective_sample_limit": 1,
        "updated_at": control.updated_at.isoformat() if control.updated_at else None,
        "updated_by": control.updated_by,
        "source": control.source,
    }


def _requested_by(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return "admin_api"
    if len(normalized) > 64 or re.fullmatch(r"[A-Za-z0-9:_-]+", normalized) is None:
        return "admin_api"
    return normalized
