from __future__ import annotations

from enum import StrEnum
from typing import Any


class ResultStatus(StrEnum):
    AVAILABLE = "available"
    COMPLETED = "completed"
    ERROR = "error"
    PARTIAL = "partial"
    PAUSED = "paused"
    REGISTERED = "registered"
    RESERVATION_UNCONFIRMED = "reservation_unconfirmed"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class OrderStateStatus(StrEnum):
    PROGRAMMED = "programmed"
    REGISTERED = "registered"
    RESERVATION_UNCONFIRMED = "reservation_unconfirmed"
    SUBMISSION_INTENT = "submission_intent"
    SUBMISSION_PENDING = "submission_pending"


SENSITIVE_DETAIL_KEYS = {
    "apellido",
    "apellidos",
    "credential",
    "credentials",
    "document",
    "documento",
    "dni",
    "email",
    "login_password",
    "login_username",
    "name",
    "nombre",
    "password",
    "secret",
    "token",
    "username",
}


def sanitize_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return None

    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        if key.strip().lower() in SENSITIVE_DETAIL_KEYS:
            continue
        sanitized[key] = _sanitize_value(value)
    return sanitized or None


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return sanitize_details(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    return value


__all__ = [
    "OrderStateStatus",
    "ResultStatus",
    "SENSITIVE_DETAIL_KEYS",
    "sanitize_details",
]
