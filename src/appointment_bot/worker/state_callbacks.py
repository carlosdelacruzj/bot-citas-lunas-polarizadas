from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.core.models import (
    AvailabilityResult,
    RunReport,
    ServiceOrderCandidate,
    ServiceOrderRuntime,
)
from appointment_bot.services.telegram_alerts import enqueue_immediate_availability
from appointment_bot.utils.sanitization import sanitize_text
from appointment_bot.worker.execution import continuous_order_settings


class WorkerStateCallbacks:
    def __init__(
        self,
        settings: Settings,
        *,
        update_state: Callable[..., None],
        reset_errors: Callable[..., None],
        extend_hot_window_after_availability: Callable[[], None],
        record_window_metric: Callable[[RunReport], None],
    ) -> None:
        self.settings = settings
        self._update_state = update_state
        self._reset_errors = reset_errors
        self._extend_hot_window_after_availability = extend_hot_window_after_availability
        self._record_window_metric = record_window_metric
        self.unavailable_streak = 0
        self._availability_alert_signatures: set[str] = set()

    def record_check(self, report: RunReport) -> None:
        self._record_window_metric(report)
        self._update_state(
            last_check_at=_now(),
            next_check_at=None,
            last_error=sanitize_text(report.message) if report.exit_code else None,
        )
        if report.status == "unavailable":
            self.unavailable_streak += 1
        elif report.status in {"available", "registered", "completed", "partial"}:
            self.unavailable_streak = 0
        if report.status in {"available", "registered"}:
            self._extend_hot_window_after_availability()

    def on_order_check(
        self,
        result: AvailabilityResult,
        attempt: int,
        next_check_seconds: int | None,
    ) -> None:
        if result.status not in {"error", "unknown", "reservation_unconfirmed"}:
            self._reset_errors(clear_session=False)
        monitoring_mode = str((result.details or {}).get("monitoring_mode") or "normal")
        self._update_state(
            phase=f"monitoring_observer_{monitoring_mode}",
            last_check_at=_now(),
            next_check_at=(_future(next_check_seconds) if next_check_seconds is not None else None),
        )
        self._notify_immediate_availability_once(result)

    def on_rapid_order_start(
        self,
        order: ServiceOrderCandidate | ServiceOrderRuntime,
    ) -> None:
        order_settings = continuous_order_settings(self.settings, order)
        self._update_state(
            phase="rapid_queue",
            current_order_id=order.order_id,
            masked_account=order_settings.safe_username,
            session_started_at=_now(),
            next_check_at=_now(),
        )

    def on_rapid_order_check(
        self,
        result: AvailabilityResult,
        attempt: int,
        next_check_seconds: int | None,
    ) -> None:
        self.on_order_check(result, attempt, next_check_seconds)

    def on_observer_check(
        self,
        result: AvailabilityResult,
        screenshot_path: Path | None,
        attempt: int,
        next_check_seconds: int | None,
    ) -> None:
        if result.status not in {"error", "unknown", "reservation_unconfirmed"}:
            self._reset_errors(clear_session=False)
        self._update_state(
            last_check_at=_now(),
            next_check_at=(_future(next_check_seconds) if next_check_seconds is not None else None),
        )
        if result.status != "available":
            if result.status == "unavailable":
                self._update_state(availability_signature=None)
            return
        self._notify_immediate_availability_once(result)
        self._extend_hot_window_after_availability()

    def reset_unavailable_streak(self) -> None:
        self.unavailable_streak = 0

    def _notify_immediate_availability_once(self, result: AvailabilityResult) -> None:
        if result.status not in {"available", "partial"}:
            return
        signature = _availability_result_signature(result)
        if signature in self._availability_alert_signatures:
            return
        self._extend_hot_window_after_availability()
        if enqueue_immediate_availability(result, dedupe_key=signature):
            self._availability_alert_signatures.add(signature)


def _availability_result_signature(result: AvailabilityResult) -> str:
    details = result.details or {}
    relevant = {
        key: details.get(key)
        for key in ("orden", "sede", "fecha", "hora", "date_options", "hour_options")
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


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _future(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(timespec="seconds")
