import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings
from appointment_bot.domain import (
    AvailabilityResult,
    RunReport,
)
from appointment_bot.flows.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    PROCESS_STAGES_SCREENSHOT_SELECTORS,
    AppointmentOptionsNotRefreshed,
    AppointmentWorkflowCancelled,
    ReservationSubmissionUncertain,
    click_program_action,
    dismiss_reservation_confirmation,
    has_available_date_options,
    open_appointment_panel,
    read_appointment_availability,
    select_available_appointment,
    select_available_site,
    solve_reservation_captcha_and_click_reserve,
    wait_for_reservation_confirmation,
)
from appointment_bot.flows.login import login
from appointment_bot.flows.stages import (
    appointment_stage_result,
    read_process_stages,
    wait_for_programmed_appointment_stage,
)
from appointment_bot.services.client_video import ClientSessionVideoRecorder
from appointment_bot.services.notifier import notify_error, notify_result
from appointment_bot.services.run_reporting import (
    finalize_report,
    report_from_result,
    reservation_confirmed,
)
from appointment_bot.utils.screenshots import (
    remove_screenshot_paths,
    report_screenshot_paths,
    save_error_screenshot,
    save_result_screenshot,
    save_screenshot,
)

logger = logging.getLogger(__name__)


def _save_relevant_result_snapshot(page, settings, status: str) -> Path | None:
    if status not in {"available", "partial"}:
        return None

    return save_result_screenshot(
        page,
        settings,
        label=f"result-{status}",
        selectors=APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    )


def _save_process_stages_snapshot(page, settings) -> Path | None:
    return save_result_screenshot(
        page,
        settings,
        label="process-stages",
        selectors=PROCESS_STAGES_SCREENSHOT_SELECTORS,
    )


def _complete_available_reservation(
    page,
    settings,
    result: AvailabilityResult,
    screenshot_path: Path | None,
    cancel_event: threading.Event | None = None,
    can_submit: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[], None] | None = None,
    on_submission_started: Callable[[], None] | None = None,
) -> tuple[AvailabilityResult, Path | None, list[Path]]:
    submission_started = False

    def mark_submission_started() -> None:
        nonlocal submission_started
        if on_submission_started is not None:
            on_submission_started()
        submission_started = True

    try:
        page = solve_reservation_captcha_and_click_reserve(
            page,
            settings,
            cancel_event=cancel_event,
            can_submit=can_submit,
            expected_details=result.details,
            on_submission_intent=on_submission_intent,
            on_submission_started=mark_submission_started,
        )
        confirmation_text_detected = wait_for_reservation_confirmation(page)
        reservation_confirmation_screenshot_path = save_screenshot(
            page,
            settings,
            "reservation-confirmation",
        )
        dismiss_reservation_confirmation(page)
        programmed_stage = wait_for_programmed_appointment_stage(page, result.details)
        updated_process_stages_screenshot_path = _save_process_stages_snapshot(
            page,
            settings,
        )
    except ReservationSubmissionUncertain as exc:
        submission_started = True
        confirmation_text_detected = False
        programmed_stage = None
        reservation_confirmation_screenshot_path = None
        updated_process_stages_screenshot_path = None
        submission_error = str(exc)
    except Exception as exc:
        if not submission_started:
            raise
        confirmation_text_detected = False
        programmed_stage = None
        reservation_confirmation_screenshot_path = None
        updated_process_stages_screenshot_path = None
        submission_error = (
            "La solicitud de reserva fue enviada, pero fallo la verificacion posterior "
            f"({type(exc).__name__})."
        )
        logger.exception("Reservation was submitted but confirmation failed")
    else:
        submission_error = None
    screenshot_paths = [
        path
        for path in [
            reservation_confirmation_screenshot_path,
            updated_process_stages_screenshot_path,
            screenshot_path,
        ]
        if path is not None
    ]
    if screenshot_paths:
        screenshot_path = screenshot_paths[0]

    details = dict(result.details or {})
    details["confirmacion_texto"] = "detectada" if confirmation_text_detected else "no detectada"
    details["confirmacion_etapa"] = (
        "Programado" if programmed_stage is not None else "no confirmada"
    )
    if submission_error:
        details["confirmacion_error"] = submission_error
    if programmed_stage is not None:
        details["fecha_programada"] = programmed_stage.date

    if programmed_stage is None:
        return (
            AvailabilityResult(
                status="reservation_unconfirmed",
                message=(
                    "Se resolvio el captcha y se hizo click en Reservar, "
                    "pero no se confirmo la etapa Programado."
                ),
                details=details,
            ),
            screenshot_path,
            screenshot_paths,
        )

    return (
        AvailabilityResult(
            status="registered",
            message=(
                "La reserva fue confirmada por la etapa Programado."
                if not confirmation_text_detected
                else "La reserva fue confirmada por mensaje y etapa Programado."
            ),
            details=details,
        ),
        screenshot_path,
        screenshot_paths,
    )


def _monitor_appointment_availability(
    page,
    settings,
    process_stages_screenshot_path,
    cancel_event: threading.Event | None = None,
    on_check: Callable[[AvailabilityResult, int, int | None], None] | None = None,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    can_submit: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[], None] | None = None,
    on_submission_started: Callable[[], None] | None = None,
):
    deadline = time.monotonic() + settings.monitor_window_seconds
    attempt = 1
    screenshot_path = None
    screenshot_paths = (
        [process_stages_screenshot_path] if process_stages_screenshot_path is not None else []
    )

    while True:
        if cancel_event is not None and cancel_event.is_set():
            return (
                AvailabilityResult(
                    status="paused",
                    message="La revision fue interrumpida por una pausa del trabajador.",
                ),
                screenshot_path,
                screenshot_paths,
            )
        logger.info("Appointment availability check attempt %s", attempt)
        try:
            page = select_available_site(
                page,
                timeout=settings.postback_timeout_seconds * 1_000,
            )
        except AppointmentOptionsNotRefreshed as exc:
            result = AvailabilityResult(status="unknown", message=str(exc))
            if on_check is not None:
                on_check(result, attempt, None)
            return result, screenshot_path, screenshot_paths
        result = read_appointment_availability(
            page,
            timeout=settings.read_timeout_seconds * 1_000,
        )

        if result.status == "unknown":
            if on_check is not None:
                on_check(result, attempt, None)
            result_screenshot_path = save_result_screenshot(
                page,
                settings,
                "result-unknown",
            )
            screenshot_path = result_screenshot_path or process_stages_screenshot_path
            return result, screenshot_path, screenshot_paths

        result_screenshot_path = _save_relevant_result_snapshot(
            page,
            settings,
            result.status,
        )
        screenshot_path = result_screenshot_path or process_stages_screenshot_path

        can_attempt_reservation = result.status == "available" or (
            result.status == "partial" and has_available_date_options(page)
        )
        if can_attempt_reservation:
            selected_result = select_available_appointment(
                page,
                is_allowed_appointment=is_allowed_appointment,
                timeout=settings.postback_timeout_seconds * 1_000,
            )
            if not settings.auto_reserve:
                if selected_result.status == "available":
                    return (
                        AvailabilityResult(
                            status="available",
                            message=(
                                "Se verificaron fecha y hora seleccionables. "
                                "La reserva automatica esta desactivada."
                            ),
                            details=selected_result.details,
                        ),
                        screenshot_path,
                        screenshot_paths,
                    )
                result = selected_result
            if selected_result.status == "available":
                if cancel_event is not None and cancel_event.is_set():
                    return (
                        AvailabilityResult(
                            status="paused",
                            message=("La pausa se aplico antes de iniciar la reserva."),
                        ),
                        screenshot_path,
                        screenshot_paths,
                    )
                if on_check is not None:
                    on_check(selected_result, attempt, None)
                try:
                    return _complete_available_reservation(
                        page,
                        settings,
                        selected_result,
                        screenshot_path,
                        cancel_event,
                        can_submit,
                        on_submission_intent,
                        on_submission_started,
                    )
                except AppointmentWorkflowCancelled as exc:
                    return (
                        AvailabilityResult(status="paused", message=str(exc)),
                        screenshot_path,
                        screenshot_paths,
                    )
            if settings.auto_reserve:
                result = selected_result

        # Una disponibilidad parcial tambien se vuelve a comprobar dentro
        # de la misma sesion; una fecha puede cargar sus horas en un intento posterior.
        if result.status not in {"unavailable", "partial"}:
            if on_check is not None:
                on_check(result, attempt, None)
            return result, screenshot_path, screenshot_paths

        # El modo rapido usa una sola revision; el monitor respeta ademas
        # un maximo explicito para no consultar la pagina indefinidamente.
        if settings.monitor_window_seconds <= 0 or attempt >= settings.monitor_max_attempts:
            if on_check is not None:
                on_check(result, attempt, None)
            return result, screenshot_path, screenshot_paths

        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            logger.info("Monitor window finished after %s attempts", attempt)
            return result, screenshot_path, screenshot_paths

        wait_seconds = min(
            random.randint(
                settings.monitor_interval_min_seconds,
                settings.monitor_interval_max_seconds,
            ),
            max(1, int(remaining_seconds)),
        )
        logger.info(
            "No appointment availability detected; waiting %s seconds before retry",
            wait_seconds,
        )
        if on_check is not None:
            on_check(result, attempt, wait_seconds)
        if cancel_event is not None:
            if cancel_event.wait(wait_seconds):
                return (
                    AvailabilityResult(
                        status="paused",
                        message="La revision fue interrumpida por una pausa del trabajador.",
                    ),
                    screenshot_path,
                    screenshot_paths,
                )
        else:
            page.wait_for_timeout(wait_seconds * 1_000)
        if time.monotonic() >= deadline:
            logger.info("Monitor window finished after %s attempts", attempt)
            return result, screenshot_path, screenshot_paths
        attempt += 1


def run_with_report(
    settings: Settings,
    *,
    order_id: str | None = None,
    client_name: str | None = None,
    cancel_event: threading.Event | None = None,
    on_check: Callable[[AvailabilityResult, int, int | None], None] | None = None,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    can_submit: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[], None] | None = None,
    on_submission_started: Callable[[], None] | None = None,
) -> RunReport:
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    started_at_dt = datetime.now()
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

        final_result = None
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
                login(page, settings)
                page = click_program_action(page)
                stages = read_process_stages(page)
                stage_result = appointment_stage_result(stages)
                if stage_result is not None:
                    stage_result = _with_client_context(
                        stage_result,
                        order_id=order_id,
                        client_name=client_name,
                        settings=settings,
                    )
                    process_stages_screenshot_path = _save_process_stages_snapshot(page, settings)
                    screenshot_path = process_stages_screenshot_path
                    notify_result(stage_result, settings, screenshot_path)
                    logger.info("Finished appointment check: %s", stage_result.status)
                    final_result = stage_result
                else:
                    process_stages_screenshot_path = None
                    page = open_appointment_panel(page)
                    result, screenshot_path, screenshot_paths = _monitor_appointment_availability(
                        page,
                        settings,
                        process_stages_screenshot_path,
                        cancel_event,
                        on_check,
                        is_allowed_appointment,
                        can_submit,
                        on_submission_intent,
                        on_submission_started,
                    )
                    result = _with_client_context(
                        result,
                        order_id=order_id,
                        client_name=client_name,
                        settings=settings,
                    )
                    notify_result(
                        result,
                        settings,
                        screenshot_path,
                        screenshot_paths=screenshot_paths,
                    )
                    logger.info("Finished appointment check: %s", result.status)
                    final_result = result
            except Exception:
                screenshot_path = save_error_screenshot(page, settings)
                raise

        if final_result is None:
            final_result = AvailabilityResult(
                status="completed",
                message="La revision termino sin devolver un resultado especifico.",
            )
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
        finalized_report = finalize_report(
            report,
            settings,
            started_at_dt=started_at_dt,
        )
        _cleanup_unconfirmed_session_screenshots(finalized_report)
        return finalized_report
    except Exception as exc:
        logger.exception("Appointment check failed")
        notify_error(exc, settings, screenshot_path)
        error_report = RunReport(
            status="error",
            message=str(exc),
            exit_code=1,
            run_id=run_id,
            order_id=order_id,
            started_at=started_at,
            screenshot_path=str(screenshot_path) if screenshot_path is not None else None,
            screenshot_paths=[str(path) for path in screenshot_paths] or None,
        )
        if video_recorder is not None:
            video_recorder.finalize(error_report)
        finalized_report = finalize_report(
            error_report,
            settings,
            started_at_dt=started_at_dt,
        )
        _cleanup_unconfirmed_session_screenshots(finalized_report)
        return finalized_report


def _cleanup_unconfirmed_session_screenshots(report: RunReport) -> None:
    if reservation_confirmed(report):
        return

    remove_screenshot_paths(report_screenshot_paths(report))


def _with_client_context(
    result: AvailabilityResult,
    *,
    order_id: str | None,
    client_name: str | None,
    settings: Settings,
) -> AvailabilityResult:
    if order_id is None:
        return result

    details = dict(result.details or {})
    details.setdefault("orden", order_id)
    details.setdefault("cuenta", settings.safe_username)
    if client_name:
        details.setdefault("cliente", client_name)
    return replace(result, details=details)
