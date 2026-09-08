import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from appointment_bot.browser.session import open_page
from appointment_bot.configuration.captcha import CaptchaSettings
from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.configuration.reservation import ReservationSettings
from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.configuration.telegram import TelegramSettings
from appointment_bot.core.models import AvailabilityResult, RunReport
from appointment_bot.reservation_engine.appointment_contracts import PortalContractChanged
from appointment_bot.reservation_engine.ports import ReservationEnginePorts, SessionVideo
from appointment_bot.reservation_engine.results import cleanup_unconfirmed_session_screenshots
from appointment_bot.reservation_engine.session_flow import execute_session_flow
from appointment_bot.utils.screenshots import save_error_screenshot

logger = logging.getLogger(__name__)


def run_with_report(
    *,
    runtime_settings: RuntimeSettings,
    reservation_settings: ReservationSettings,
    captcha_settings: CaptchaSettings,
    evidence_settings: EvidenceSettings,
    telegram_settings: TelegramSettings,
    order_id: str | None = None,
    client_name: str | None = None,
    cancel_event: threading.Event | None = None,
    on_check: Callable[[AvailabilityResult, int, int | None], None] | None = None,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    can_submit: Callable[[], bool] | None = None,
    can_solve_captcha: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[dict | None], None] | None = None,
    on_submission_started: Callable[[dict | None], None] | None = None,
    on_submission_resolved: Callable[[str, str | None, str | None], None] | None = None,
    expected_person_name: str | None = None,
    program_expediente: str | None = None,
    program_plate: str | None = None,
    notify_mode: str = "full",
    ports: ReservationEnginePorts,
) -> RunReport:
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    evidence_settings = replace(
        evidence_settings,
        artifact_prefix="-".join(part for part in (run_id, order_id or "observer") if part),
    )
    started_at_dt = datetime.now(UTC)
    started_at = started_at_dt.isoformat(timespec="seconds")
    screenshot_path = None
    screenshot_paths = []
    video_recorder: SessionVideo | None = None
    try:
        video_recorder = ports.runs.create_video(
            order_id=order_id or run_id,
            client_name=client_name or "observer",
            started_at=started_at_dt,
            evidence_settings=evidence_settings,
        )
        logger.info("Starting appointment check for %s", reservation_settings.target_url)
        logger.info(
            "Reservation policy: auto_reserve=%s record_client_sessions=%s",
            reservation_settings.auto_reserve,
            evidence_settings.record_client_sessions,
        )
        logger.info("Using login username %s", reservation_settings.safe_username)

        if cancel_event is not None and cancel_event.is_set():
            if video_recorder is not None:
                video_recorder.cleanup()
            return ports.runs.finalize_report(
                RunReport(
                    status="paused",
                    message="El trabajador esta pausado.",
                    exit_code=0,
                    run_id=run_id,
                    order_id=order_id,
                    started_at=started_at,
                ),
                started_at_dt=started_at_dt,
                runtime_settings=runtime_settings,
                evidence_settings=evidence_settings,
            )

        with (
            open_page(
                video_dir=(video_recorder.record_video_dir if video_recorder is not None else None),
                video_width=evidence_settings.client_video_width,
                video_height=evidence_settings.client_video_height,
                video_path_callback=(
                    video_recorder.capture_source_path if video_recorder is not None else None
                ),
                runtime_settings=runtime_settings,
                evidence_settings=evidence_settings,
            ) as page,
        ):
            try:
                flow_result = execute_session_flow(
                    page,
                    run_id=run_id,
                    order_id=order_id,
                    client_name=client_name,
                    cancel_event=cancel_event,
                    on_check=on_check,
                    is_allowed_appointment=is_allowed_appointment,
                    can_submit=can_submit,
                    can_solve_captcha=can_solve_captcha,
                    on_submission_intent=on_submission_intent,
                    on_submission_started=on_submission_started,
                    on_submission_resolved=on_submission_resolved,
                    expected_person_name=expected_person_name,
                    program_expediente=program_expediente,
                    program_plate=program_plate,
                    notify_mode=notify_mode,
                    ports=ports,
                    runtime_settings=runtime_settings,
                    reservation_settings=reservation_settings,
                    captcha_settings=captcha_settings,
                    evidence_settings=evidence_settings,
                    telegram_settings=telegram_settings,
                )
                final_result = flow_result.final_result
                screenshot_path = flow_result.screenshot_path
                screenshot_paths = flow_result.screenshot_paths
            except Exception:
                screenshot_path = save_error_screenshot(
                    page, "error-flujo-principal", evidence_settings=evidence_settings
                )
                raise

        return _finalize_successful_run(
            final_result,
            run_id=run_id,
            order_id=order_id,
            started_at=started_at,
            started_at_dt=started_at_dt,
            screenshot_path=screenshot_path,
            screenshot_paths=screenshot_paths,
            video_recorder=video_recorder,
            notify_mode=notify_mode,
            ports=ports,
            runtime_settings=runtime_settings,
            evidence_settings=evidence_settings,
        )
    except Exception as exc:
        return _finalize_failed_run(
            exc,
            run_id=run_id,
            order_id=order_id,
            started_at=started_at,
            started_at_dt=started_at_dt,
            screenshot_path=screenshot_path,
            screenshot_paths=screenshot_paths,
            video_recorder=video_recorder,
            notify_mode=notify_mode,
            ports=ports,
            runtime_settings=runtime_settings,
            evidence_settings=evidence_settings,
            telegram_settings=telegram_settings,
        )


def _finalize_successful_run(
    final_result: AvailabilityResult,
    *,
    runtime_settings: RuntimeSettings,
    evidence_settings: EvidenceSettings,
    run_id: str,
    order_id: str | None,
    started_at: str,
    started_at_dt: datetime,
    screenshot_path,
    screenshot_paths: list,
    video_recorder: SessionVideo | None,
    notify_mode: str,
    ports: ReservationEnginePorts,
) -> RunReport:
    report = ports.runs.report_from_result(
        final_result,
        run_id=run_id,
        order_id=order_id,
        started_at=started_at,
        screenshot_path=screenshot_path,
        screenshot_paths=screenshot_paths,
    )
    if video_recorder is not None:
        video_path = video_recorder.finalize(report)
        if video_path is not None:
            logger.info("Client session video saved: %s", video_path)
            report = replace(
                report,
                details={**(report.details or {}), "video_path": str(video_path)},
            )
    finalized_report = ports.runs.finalize_report(
        report,
        started_at_dt=started_at_dt,
        runtime_settings=runtime_settings,
        evidence_settings=evidence_settings,
    )
    if notify_mode == "full":
        cleanup_unconfirmed_session_screenshots(finalized_report)
    return finalized_report


def _finalize_failed_run(
    error: Exception,
    *,
    runtime_settings: RuntimeSettings,
    evidence_settings: EvidenceSettings,
    telegram_settings: TelegramSettings,
    run_id: str,
    order_id: str | None,
    started_at: str,
    started_at_dt: datetime,
    screenshot_path,
    screenshot_paths: list,
    video_recorder: SessionVideo | None,
    notify_mode: str,
    ports: ReservationEnginePorts,
) -> RunReport:
    logger.exception("Appointment check failed")
    error_report = RunReport(
        status="error",
        message=str(error),
        exit_code=1,
        run_id=run_id,
        order_id=order_id,
        started_at=started_at,
        details={
            "error_type": type(error).__name__,
            "worker_pause_required": isinstance(error, PortalContractChanged),
        },
        screenshot_path=str(screenshot_path) if screenshot_path is not None else None,
        screenshot_paths=[str(path) for path in screenshot_paths] or None,
    )
    if video_recorder is not None:
        video_path = video_recorder.finalize(error_report)
        if video_path is not None:
            logger.info("Diagnostic session video saved: %s", video_path)
            error_report = replace(
                error_report,
                details={**(error_report.details or {}), "video_path": str(video_path)},
            )
    finalized_report = ports.runs.finalize_report(
        error_report,
        started_at_dt=started_at_dt,
        runtime_settings=runtime_settings,
        evidence_settings=evidence_settings,
    )
    ports.alerts.notify_error(error, screenshot_path, telegram_settings=telegram_settings)
    if notify_mode == "full":
        cleanup_unconfirmed_session_screenshots(finalized_report)
    return finalized_report
