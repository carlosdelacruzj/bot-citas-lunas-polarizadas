from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from appointment_bot.utils.sanitization import sanitize_text


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


class ClientStateStatus(StrEnum):
    PROGRAMMED = "programmed"
    REGISTERED = "registered"
    RESERVATION_UNCONFIRMED = "reservation_unconfirmed"
    SUBMISSION_INTENT = "submission_intent"
    SUBMISSION_PENDING = "submission_pending"


@dataclass(frozen=True)
class AvailabilityResult:
    status: ResultStatus
    message: str
    details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ResultStatus(self.status))


@dataclass(frozen=True)
class RunReport:
    status: ResultStatus
    message: str
    exit_code: int
    run_id: str | None = None
    client_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    reservation_attempted: bool = False
    reservation_confirmed: bool = False
    details: dict[str, Any] | None = None
    screenshot_path: str | None = None
    screenshot_paths: list[str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ResultStatus(self.status))


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


def public_report_dict(report: RunReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["status"] = report.status.value
    payload["message"] = sanitize_text(report.message)
    payload["details"] = sanitize_details(report.details)
    payload["screenshot_path"] = _public_path(report.screenshot_path)
    payload["screenshot_paths"] = [
        path
        for path in (_public_path(item) for item in report.screenshot_paths or [])
        if path is not None
    ] or None
    return payload


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return sanitize_details(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    return value


def _public_path(value: str | None) -> str | None:
    if not value:
        return None
    return Path(value).name
