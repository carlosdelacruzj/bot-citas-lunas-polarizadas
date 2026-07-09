import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult, RunReport
from appointment_bot.services.client_video import ClientSessionVideoRecorder
from appointment_bot.services.notifier import notify_error
from appointment_bot.services.run_reporting import finalize_report, report_from_result
from appointment_bot.services.session_flow import execute_session_flow
from appointment_bot.services.session_results import cleanup_unconfirmed_session_screenshots
from appointment_bot.utils.screenshots import save_error_screenshot

logger = logging.getLogger(__name__)


def run_with_report(
    settings: Settings,
    *,
    order_id: str | None = None,
    client_name: str | None = None,
    cancel_event: threading.Event | None = None,
    on_check: Callable[[AvailabilityResult, int, int | None], None] | None = None,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    can_submit: Callable[[], bool] | None = None,
    can_solve_captcha: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[dict | None], None] | None = None,
    on_submission_started: Callable[[dict | None], None] | None = None,
    expected_person_name: str | None = None,
    program_expediente: str | None = None,
    program_plate: str | None = None,
    notify_mode: str = "full",
) -> RunReport:
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    settings = replace(
        settings,
        artifact_prefix="-".join(part for part in (run_id, order_id or "observer") if part),
    )
    started_at_dt = datetime.now(UTC)
    started_at = started_at_dt.isoformat(timespec="seconds")
    screenshot_path = None
    screenshot_paths = []
    video_recorder: ClientSessionVideoRecorder | None = None
    try:
        video_recorder = ClientSessionVideoRecorder.create(
            settings,
            order_id=order_id,
            client_name=client_name,
            started_at=started_at_dt,
        )
        logger.info("Starting appointment check for %s", settings.target_url)
        logger.info("Using login username %s", settings.safe_username)

        if cancel_event is not None and cancel_event.is_set():
            if video_recorder is not None:
                video_recorder.cleanup()
            return finalize_report(
                RunReport(
                    status="paused",
                    message="El trabajador esta pausado.",
                    exit_code=0,
                    run_id=run_id,
                    order_id=order_id,
                    started_at=started_at,
                ),
                settings,
                started_at_dt=started_at_dt,
            )

        with (
            open_page(
                settings,
                init_script=(video_recorder.init_script if video_recorder is not None else None),
                video_dir=(video_recorder.record_video_dir if video_recorder is not None else None),
                video_width=settings.client_video_width,
                video_height=settings.client_video_height,
                video_path_callback=(
                    video_recorder.capture_source_path if video_recorder is not None else None
                ),
            ) as page,
        ):
            try:
                flow_result = execute_session_flow(
                    page,
                    settings,
                    order_id=order_id,
                    client_name=client_name,
                    cancel_event=cancel_event,
                    on_check=on_check,
                    is_allowed_appointment=is_allowed_appointment,
                    can_submit=can_submit,
                    can_solve_captcha=can_solve_captcha,
                    on_submission_intent=on_submission_intent,
                    on_submission_started=on_submission_started,
                    expected_person_name=expected_person_name,
                    program_expediente=program_expediente,
                    program_plate=program_plate,
                    notify_mode=notify_mode,
                )
                final_result = flow_result.final_result
                screenshot_path = flow_result.screenshot_path
                screenshot_paths = flow_result.screenshot_paths
            except Exception:
                screenshot_path = save_error_screenshot(page, settings, "error-flujo-principal")
                raise

        return _finalize_successful_run(
            final_result,
            settings,
            run_id=run_id,
            order_id=order_id,
            started_at=started_at,
            started_at_dt=started_at_dt,
            screenshot_path=screenshot_path,
            screenshot_paths=screenshot_paths,
            video_recorder=video_recorder,
            notify_mode=notify_mode,
        )
    except Exception as exc:
        return _finalize_failed_run(
            exc,
            settings,
            run_id=run_id,
            order_id=order_id,
            started_at=started_at,
            started_at_dt=started_at_dt,
            screenshot_path=screenshot_path,
            screenshot_paths=screenshot_paths,
            video_recorder=video_recorder,
            notify_mode=notify_mode,
        )


def _finalize_successful_run(
    final_result: AvailabilityResult,
    settings: Settings,
    *,
    run_id: str,
    order_id: str | None,
    started_at: str,
    started_at_dt: datetime,
    screenshot_path,
    screenshot_paths: list,
    video_recorder: ClientSessionVideoRecorder | None,
    notify_mode: str,
) -> RunReport:
    report = report_from_result(
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
    finalized_report = finalize_report(report, settings, started_at_dt=started_at_dt)
    if notify_mode == "full":
        cleanup_unconfirmed_session_screenshots(finalized_report)
    return finalized_report


def _finalize_failed_run(
    error: Exception,
    settings: Settings,
    *,
    run_id: str,
    order_id: str | None,
    started_at: str,
    started_at_dt: datetime,
    screenshot_path,
    screenshot_paths: list,
    video_recorder: ClientSessionVideoRecorder | None,
    notify_mode: str,
) -> RunReport:
    logger.exception("Appointment check failed")
    notify_error(error, settings, screenshot_path)
    error_report = RunReport(
        status="error",
        message=str(error),
        exit_code=1,
        run_id=run_id,
        order_id=order_id,
        started_at=started_at,
        details={"error_type": type(error).__name__},
        screenshot_path=str(screenshot_path) if screenshot_path is not None else None,
        screenshot_paths=[str(path) for path in screenshot_paths] or None,
    )
    if video_recorder is not None:
        video_recorder.finalize(error_report)
    finalized_report = finalize_report(error_report, settings, started_at_dt=started_at_dt)
    if notify_mode == "full":
        cleanup_unconfirmed_session_screenshots(finalized_report)
    return finalized_report
