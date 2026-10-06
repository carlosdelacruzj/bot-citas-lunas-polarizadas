from __future__ import annotations

from collections.abc import Mapping
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
    "answer",
    "solution",
    "captcha_solution_sent",
    "external_answer",
    "human_label_answer",
}

SENSITIVE_DETAIL_KEY_FRAGMENTS = (
    "password",
    "credential",
    "secret",
    "token",
)

CAPTCHA_ANSWER_DETAIL_KEYS = {
    "answer",
    "solution",
    "captcha_solution_sent",
    "external_answer",
    "human_label_answer",
}


def sanitize_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return None

    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        normalized_key = str(key).strip().lower()
        if _sensitive_detail_key(normalized_key):
            continue
        sanitized[str(key)] = _sanitize_value(value)
    return sanitized or None


def redact_captcha_answers(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return None

    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        normalized_key = str(key).strip().lower()
        if _captcha_answer_key(normalized_key):
            continue
        sanitized[str(key)] = _redact_captcha_value(value)
    return sanitized or None


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return sanitize_details(dict(value))
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, set):
        return [_sanitize_value(item) for item in sorted(value, key=str)]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "[binary redacted]"
    return value


def _redact_captcha_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return redact_captcha_answers(dict(value))
    if isinstance(value, list):
        return [_redact_captcha_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_captcha_value(item) for item in value]
    if isinstance(value, set):
        return [_redact_captcha_value(item) for item in sorted(value, key=str)]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "[binary redacted]"
    return value


def _sensitive_detail_key(key: str) -> bool:
    if key in SENSITIVE_DETAIL_KEYS:
        return True
    if any(fragment in key for fragment in SENSITIVE_DETAIL_KEY_FRAGMENTS):
        return True
    return "captcha" in key and any(marker in key for marker in ("answer", "solution", "response"))


def _captcha_answer_key(key: str) -> bool:
    if key in CAPTCHA_ANSWER_DETAIL_KEYS:
        return True
    return "captcha" in key and any(marker in key for marker in ("answer", "solution", "response"))


__all__ = [
    "OrderStateStatus",
    "ResultStatus",
    "SENSITIVE_DETAIL_KEYS",
    "SENSITIVE_DETAIL_KEY_FRAGMENTS",
    "CAPTCHA_ANSWER_DETAIL_KEYS",
    "redact_captcha_answers",
    "sanitize_details",
]
