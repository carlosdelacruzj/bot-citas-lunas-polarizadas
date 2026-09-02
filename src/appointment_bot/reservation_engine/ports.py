from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from appointment_bot.config import Settings
from appointment_bot.core.models import AvailabilityResult, RunReport


@dataclass(frozen=True, slots=True)
class CaptchaSolveResult:
    answer: str
    source: str
    decision_id: str | None
    fallback_reason: str | None
    local_request_ms: float | None = None
    local_inference_ms: float | None = None
    mean_confidence: float | None = None
    min_char_confidence: float | None = None
    sequence_confidence_product: float | None = None
    local_queue_wait_ms: float | None = None
    local_preprocess_ms: float | None = None
    local_persist_ms: float | None = None
    local_service_total_ms: float | None = None
    local_cached: bool | None = None
    local_coalesced: bool | None = None


class SessionVideo(Protocol):
    @property
    def record_video_dir(self) -> Path: ...

    def capture_source_path(self, path: Path | None) -> None: ...

    def finalize(self, report: RunReport) -> Path | None: ...

    def cleanup(self) -> None: ...


class RunSink(Protocol):
    def report_from_result(self, result: AvailabilityResult, **kwargs: Any) -> RunReport: ...

    def finalize_report(
        self,
        report: RunReport,
        settings: Settings,
        *,
        started_at_dt: datetime,
    ) -> RunReport: ...

    def create_video(
        self,
        settings: Settings,
        *,
        order_id: str | None,
        client_name: str | None,
        started_at: datetime,
    ) -> SessionVideo | None: ...


class AlertSink(Protocol):
    def notify_result(
        self,
        result: AvailabilityResult,
        settings: Settings,
        screenshot_path: Path | None,
        *,
        screenshot_paths: list[Path] | None = None,
    ) -> None: ...

    def notify_error(
        self,
        error: Exception,
        settings: Settings,
        screenshot_path: Path | None,
    ) -> None: ...

    def notify_programs(
        self,
        settings: Settings,
        order_id: str | None,
        client_name: str | None,
        details: dict[str, Any],
    ) -> None: ...

    def graphic_captcha_returned(self) -> None: ...


class CaptchaAuthority(Protocol):
    def solve(
        self,
        image_path: Path,
        settings: Settings,
        **kwargs: Any,
    ) -> CaptchaSolveResult: ...

    def enqueue_prediction(self, **kwargs: Any) -> bool: ...

    def enqueue_external_result(self, **kwargs: Any) -> bool: ...

    def resolve_portal_outcome(self, event_id: str, *, portal_outcome: str) -> None: ...

    def sample_limit(self, settings: Settings) -> int: ...


class OpportunityControl(Protocol):
    def admission_allowed(self, feature: str, settings: Settings) -> bool: ...

    def record_event(self, **kwargs: Any) -> None: ...

    def trip_breaker(
        self,
        reason: str,
        burst_id: str | None,
        settings: Settings,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ReservationEnginePorts:
    runs: RunSink
    alerts: AlertSink
    captcha: CaptchaAuthority
    opportunities: OpportunityControl
