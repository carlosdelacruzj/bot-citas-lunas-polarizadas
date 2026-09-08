from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from appointment_bot.configuration.captcha import CaptchaSettings
from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.configuration.reservation import ReservationSettings
from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.configuration.telegram import TelegramSettings
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
        *,
        runtime_settings: RuntimeSettings,
        evidence_settings: EvidenceSettings,
        started_at_dt: datetime,
    ) -> RunReport: ...

    def create_video(
        self,
        *,
        evidence_settings: EvidenceSettings,
        order_id: str | None,
        client_name: str | None,
        started_at: datetime,
    ) -> SessionVideo | None: ...


class AlertSink(Protocol):
    def notify_result(
        self,
        result: AvailabilityResult,
        screenshot_path: Path | None,
        *,
        telegram_settings: TelegramSettings,
        screenshot_paths: list[Path] | None = None,
    ) -> None: ...

    def notify_error(
        self, error: Exception, screenshot_path: Path | None, *, telegram_settings: TelegramSettings
    ) -> None: ...

    def notify_programs(
        self,
        order_id: str | None,
        client_name: str | None,
        details: dict[str, Any],
        *,
        runtime_settings: RuntimeSettings,
        telegram_settings: TelegramSettings,
    ) -> None: ...

    def graphic_captcha_returned(self) -> None: ...


class CaptchaAuthority(Protocol):
    def solve(
        self,
        image_path: Path,
        *,
        runtime_settings: RuntimeSettings,
        reservation_settings: ReservationSettings,
        captcha_settings: CaptchaSettings,
        **kwargs: Any,
    ) -> CaptchaSolveResult: ...

    def enqueue_prediction(self, **kwargs: Any) -> bool: ...

    def enqueue_external_result(self, **kwargs: Any) -> bool: ...

    def resolve_portal_outcome(self, event_id: str, *, portal_outcome: str) -> None: ...

    def sample_limit(
        self, *, runtime_settings: RuntimeSettings, captcha_settings: CaptchaSettings
    ) -> int: ...


class OpportunityControl(Protocol):
    def admission_allowed(self, feature: str, *, runtime_settings: RuntimeSettings) -> bool: ...

    def record_event(self, *, runtime_settings: RuntimeSettings, **kwargs: Any) -> None: ...

    def trip_breaker(
        self, reason: str, burst_id: str | None, *, runtime_settings: RuntimeSettings
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ReservationEnginePorts:
    runs: RunSink
    alerts: AlertSink
    captcha: CaptchaAuthority
    opportunities: OpportunityControl
