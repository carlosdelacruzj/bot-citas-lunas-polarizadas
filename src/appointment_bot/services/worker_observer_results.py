from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.db.worker_state import get_worker_state
from appointment_bot.domain import AvailabilityResult, RunReport
from appointment_bot.services.notifier import notify_result
from appointment_bot.utils.screenshots import (
    remove_screenshot_paths,
    report_screenshot_paths,
)


@dataclass(frozen=True)
class ObserverReportDecision:
    confirmation_required: bool = False
    clear_availability_signature: bool = False
    reset_errors: bool = False
    error_report: RunReport | None = None
    notify_confirmed_report: RunReport | None = None


def decide_observer_report(report: RunReport) -> ObserverReportDecision:
    if report.status == "paused":
        return ObserverReportDecision()
    if report.status == "available":
        return ObserverReportDecision(confirmation_required=True)
    if report.status in {"unavailable", "partial"}:
        return ObserverReportDecision(
            clear_availability_signature=True,
            reset_errors=True,
        )
    return ObserverReportDecision(error_report=report)


def decide_observer_confirmation(report: RunReport) -> ObserverReportDecision:
    if report.status == "available":
        return ObserverReportDecision(
            notify_confirmed_report=report,
            reset_errors=True,
        )
    if report.status in {"unavailable", "partial"}:
        return ObserverReportDecision(
            clear_availability_signature=True,
            reset_errors=True,
        )
    return ObserverReportDecision(
        clear_availability_signature=True,
        error_report=report,
    )


def notify_confirmed_observer_availability(
    settings: Settings,
    report: RunReport,
) -> str | None:
    signature = availability_signature(report)
    state = get_worker_state(settings)
    if signature == state.availability_signature:
        remove_screenshot_paths(report_screenshot_paths(report))
        return None
    result = AvailabilityResult(
        status=report.status,
        message=report.message,
        details=report.details,
    )
    screenshot_path = Path(report.screenshot_path) if report.screenshot_path else None
    delivered = notify_result(result, settings, screenshot_path)
    remove_screenshot_paths(report_screenshot_paths(report))
    if delivered or not settings.telegram_enabled:
        return signature
    return None


def availability_signature(report: RunReport) -> str:
    details = report.details or {}
    relevant = {
        key: details.get(key)
        for key in ("sede", "fecha", "hora", "date_options", "hour_options")
        if details.get(key) is not None
    }
    payload = json.dumps(_normalize_signature_value(relevant), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_signature_value(value):
    if isinstance(value, dict):
        return {key: _normalize_signature_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        normalized = [_normalize_signature_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return value
