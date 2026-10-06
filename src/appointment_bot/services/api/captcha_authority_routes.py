from __future__ import annotations

import re
from http import HTTPStatus
from typing import Any

from appointment_bot.db.captcha_authority import (
    CaptchaAuthorityControl,
    get_captcha_authority_control,
    update_captcha_authority_control,
)
from appointment_bot.services.api.http import error_payload


def captcha_authority_control_payload() -> tuple[HTTPStatus, dict[str, Any]]:
    return HTTPStatus.OK, _public_payload(get_captcha_authority_control())


def update_captcha_authority_control_payload(
    body: dict[str, Any],
    *,
    requested_by: str | None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    current = get_captcha_authority_control()
    mode = body.get("mode")
    canary_limit = body.get("canary_limit", current.canary_limit)
    min_confidence = body.get(
        "min_char_confidence", current.min_char_confidence
    )
    product_confidence = body.get(
        "sequence_confidence_product", current.sequence_confidence_product
    )
    timeout_ms = body.get("timeout_ms", current.timeout_ms)
    reset_circuit = body.get("reset_circuit", False)
    reset_counters = body.get("reset_counters", False)
    field_errors: dict[str, str] = {}
    if mode not in {"2captcha", "canary"}:
        field_errors["mode"] = "Debe ser 2captcha o canary."
    if isinstance(canary_limit, bool) or not isinstance(canary_limit, int):
        field_errors["canary_limit"] = "Debe ser un entero entre 1 y 100."
    elif not 1 <= canary_limit <= 100:
        field_errors["canary_limit"] = "Debe estar entre 1 y 100."
    _validate_confidence(
        "min_char_confidence", min_confidence, field_errors
    )
    _validate_confidence(
        "sequence_confidence_product", product_confidence, field_errors
    )
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
        field_errors["timeout_ms"] = "Debe ser un entero entre 100 y 2000."
    elif not 100 <= timeout_ms <= 2000:
        field_errors["timeout_ms"] = "Debe estar entre 100 y 2000."
    if not isinstance(reset_circuit, bool):
        field_errors["reset_circuit"] = "Debe ser verdadero o falso."
    if not isinstance(reset_counters, bool):
        field_errors["reset_counters"] = "Debe ser verdadero o falso."
    if field_errors:
        payload = error_payload("bad_request", "Revisa el control de autoridad CAPTCHA.")
        payload["field_errors"] = field_errors
        return HTTPStatus.BAD_REQUEST, payload

    control = update_captcha_authority_control(
        mode=mode,
        canary_limit=canary_limit,
        min_char_confidence=float(min_confidence),
        sequence_confidence_product=float(product_confidence),
        timeout_ms=timeout_ms,
        updated_by=_requested_by(requested_by),
        reset_circuit=reset_circuit,
        reset_counters=reset_counters,
    )
    return HTTPStatus.OK, _public_payload(control)


def _public_payload(control: CaptchaAuthorityControl) -> dict[str, Any]:
    return {
        "mode": control.mode,
        "canary_limit": control.canary_limit,
        "local_decisions": control.local_decisions,
        "local_confirmed": control.local_confirmed,
        "local_rejected": control.local_rejected,
        "fallback_decisions": control.fallback_decisions,
        "remaining_local_decisions": control.remaining_local_decisions,
        "local_admission_open": control.local_admission_open,
        "min_char_confidence": control.min_char_confidence,
        "sequence_confidence_product": control.sequence_confidence_product,
        "timeout_ms": control.timeout_ms,
        "circuit_state": control.circuit_state,
        "circuit_reason": control.circuit_reason,
        "circuit_opened_at": (
            control.circuit_opened_at.isoformat() if control.circuit_opened_at else None
        ),
        "activated_at": control.activated_at.isoformat() if control.activated_at else None,
        "updated_at": control.updated_at.isoformat(),
        "updated_by": control.updated_by,
        "applies_from": "next_reservation_captcha",
        "rollback": {"mode": "2captcha"},
    }


def _validate_confidence(
    field: str,
    value: object,
    errors: dict[str, str],
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors[field] = "Debe ser un numero entre 0 y 1."
    elif not 0 <= float(value) <= 1:
        errors[field] = "Debe estar entre 0 y 1."


def _requested_by(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return "admin_api"
    if len(normalized) > 64 or re.fullmatch(r"[A-Za-z0-9:_-]+", normalized) is None:
        return "admin_api"
    return normalized
