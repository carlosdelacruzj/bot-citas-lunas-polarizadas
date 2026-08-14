from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

LIMA_TZ = ZoneInfo("America/Lima")
TIMING_DETAILS_KEY = "reservation_timing"


@dataclass
class ReservationTiming:
    available_detected_monotonic: float = field(default_factory=time.monotonic)
    available_detected_at_lima: str = field(default_factory=lambda: _lima_now())
    marks: dict[str, float] = field(default_factory=dict)
    timestamps_lima: dict[str, str] = field(default_factory=dict)

    def mark(self, name: str) -> None:
        self.marks[name] = time.monotonic()
        self.timestamps_lima[name] = _lima_now()

    def details(self) -> dict[str, Any]:
        return {
            "available_detected_at_lima": self.available_detected_at_lima,
            "reservation_finished_at_lima": self.timestamps_lima.get(
                "reservation_finished"
            ),
            "total_from_available_seconds": self._duration_from_available(
                "reservation_finished"
            ),
            "selection_seconds": self._duration("selection_started", "selection_finished"),
            "captcha_image_seconds": self._duration(
                "captcha_image_started", "captcha_image_finished"
            ),
            "captcha_solver_seconds": self._duration(
                "captcha_solver_started", "captcha_solver_finished"
            ),
            "initial_validation_seconds": self._duration(
                "initial_validation_started", "initial_validation_finished"
            ),
            "post_solver_validation_seconds": self._duration(
                "post_solver_validation_started", "post_solver_validation_finished"
            ),
            "captcha_field_fill_seconds": self._duration(
                "captcha_field_fill_started", "captcha_filled"
            ),
            "pre_click_validation_seconds": self._duration(
                "pre_click_validation_started", "pre_click_validation_finished"
            ),
            "submission_intent_seconds": self._duration(
                "submission_intent_started", "submission_intent_finished"
            ),
            "captcha_fill_to_click_seconds": self._duration(
                "captcha_filled", "reserve_click_started"
            ),
            "click_to_portal_response_seconds": self._duration(
                "reserve_click_started", "portal_response"
            ),
            "click_to_confirmation_screenshot_seconds": self._duration(
                "reserve_click_started", "confirmation_screenshot_saved"
            ),
            "post_confirmation_seconds": self._duration(
                "confirmation_screenshot_saved", "reservation_finished"
            ),
            "marks_lima": dict(self.timestamps_lima),
        }

    def _duration(self, start: str, end: str) -> float | None:
        if start not in self.marks or end not in self.marks:
            return None
        return _round_seconds(self.marks[end] - self.marks[start])

    def _duration_from_available(self, end: str) -> float | None:
        if end not in self.marks:
            return None
        return _round_seconds(self.marks[end] - self.available_detected_monotonic)


def add_reservation_timing_details(
    details: dict[str, Any] | None,
    timing: ReservationTiming | None,
) -> dict[str, Any]:
    updated = dict(details or {})
    if timing is not None:
        updated[TIMING_DETAILS_KEY] = timing.details()
    return updated


def _lima_now() -> str:
    return datetime.now(LIMA_TZ).isoformat(timespec="seconds")


def _round_seconds(value: float) -> float:
    return round(max(value, 0.0), 3)
