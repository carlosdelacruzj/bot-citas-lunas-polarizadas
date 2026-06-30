import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
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
    wait_for_reservation_submission_outcome,
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


def _confirm_programmed_stage_after_submission(
    page,
    settings,
    expected_details: dict[str, str] | None,
    *,
    confirmation_text_detected: bool,
) -> tuple[object | None, str]:
    if not confirmation_text_detected:
        stage = wait_for_programmed_appointment_stage(page, expected_details)
        return stage, "programmed_stage" if stage is not None else "unconfirmed"

    stage = wait_for_programmed_appointment_stage(page, expected_details, timeout=3_000)
    if stage is not None:
        return stage, "programmed_stage"

    if _reopen_process_detail_from_listing(page):
        stage = wait_for_programmed_appointment_stage(page, expected_details, timeout=7_000)
        if stage is not None:
            return stage, "programmed_stage_after_listing"

    if _relogin_and_reopen_process_detail(page, settings):
        stage = wait_for_programmed_appointment_stage(page, expected_details, timeout=10_000)
        if stage is not None:
            return stage, "programmed_stage_after_relogin"

    return None, "success_text_revalidation_inconclusive"


def _reopen_process_detail_from_listing(page) -> bool:
    try:
        click_program_action(page)
        return True
    except Exception:
        logger.exception("Could not reopen process detail from request listing")
        return False


def _relogin_and_reopen_process_detail(page, settings) -> bool:
    logger.info("Reopening session to validate programmed appointment stage")
    try:
        _clear_browser_session(page)
        login(page, settings)
        click_program_action(page)
        return True
    except Exception:
        logger.exception("Could not validate programmed appointment stage after relogin")
        return False


def _clear_browser_session(page) -> None:
    try:
        page.context.clear_cookies()
    except Exception:
        logger.exception("Could not clear browser cookies before relogin")
    try:
        page.goto("about:blank", wait_until="domcontentloaded", timeout=5_000)
    except Exception:
        logger.exception("Could not navigate away before relogin")


def _complete_available_reservation(
    page,
    settings,
    result: AvailabilityResult,
    screenshot_path: Path | None,
    cancel_event: threading.Event | None = None,
    can_submit: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[dict | None], None] | None = None,
    on_submission_started: Callable[[dict | None], None] | None = None,
    expected_person_name: str | None = None,
) -> tuple[AvailabilityResult, Path | None, list[Path]]:
    submission_started = False
    confirmation_source = "unconfirmed"

    def mark_submission_started() -> None:
        nonlocal submission_started
        if on_submission_started is not None:
            on_submission_started(result.details)
        submission_started = True

    try:

        def mark_submission_intent() -> None:
            if on_submission_intent is not None:
                on_submission_intent(result.details)

        page = solve_reservation_captcha_and_click_reserve(
            page,
            settings,
            cancel_event=cancel_event,
            can_submit=can_submit,
            expected_details=result.details,
            expected_person_name=expected_person_name,
            on_submission_intent=mark_submission_intent,
            on_submission_started=mark_submission_started,
        )
        submission_outcome = wait_for_reservation_submission_outcome(page)
        confirmation_text_detected = submission_outcome == "confirmed"
        reservation_confirmation_screenshot_path = save_screenshot(
            page,
            settings,
            "reservation-confirmation",
        )
        if submission_outcome != "unknown":
            dismiss_reservation_confirmation(page)
        if submission_outcome in {"captcha_invalid", "slot_lost", "rejected"}:
            details = dict(result.details or {})
            details["submission_outcome"] = submission_outcome
            messages = {
                "captcha_invalid": "El portal rechazo el captcha de la reserva.",
                "slot_lost": "El cupo dejo de estar disponible antes de completar la reserva.",
                "rejected": "El portal rechazo explicitamente la solicitud de reserva.",
            }
            return (
                AvailabilityResult(
                    status="unavailable" if submission_outcome == "slot_lost" else "error",
                    message=messages[submission_outcome],
                    details=details,
                ),
                reservation_confirmation_screenshot_path or screenshot_path,
                [
                    path
                    for path in [reservation_confirmation_screenshot_path, screenshot_path]
                    if path is not None
                ],
            )
        programmed_stage, confirmation_source = _confirm_programmed_stage_after_submission(
            page,
            settings,
            result.details,
            confirmation_text_detected=confirmation_text_detected,
        )
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
    details["submission_outcome"] = (
        "confirmed" if programmed_stage is not None or confirmation_text_detected else "unknown"
    )
    details["confirmacion_texto"] = "detectada" if confirmation_text_detected else "no detectada"
    details["confirmacion_etapa"] = (
        "Programado" if programmed_stage is not None else "no confirmada"
    )
    details["confirmation_source"] = confirmation_source
    if submission_error:
        details["confirmacion_error"] = submission_error
    if programmed_stage is not None:
        details["fecha_programada"] = programmed_stage.date

    if programmed_stage is None:
        if confirmation_text_detected:
            return (
                AvailabilityResult(
                    status="registered",
                    message=(
                        "La reserva fue registrada por mensaje de exito del portal, "
                        "pero la revalidacion de etapa Programado quedo inconclusa."
                    ),
                    details=details,
                ),
                screenshot_path,
                screenshot_paths,
            )
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
    on_submission_intent: Callable[[dict | None], None] | None = None,
    on_submission_started: Callable[[dict | None], None] | None = None,
    expected_person_name: str | None = None,
):
    deadline = time.monotonic() + settings.monitor_window_seconds
    session_started = time.monotonic()
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
        check_started = time.monotonic()
        logger.info("Appointment availability check attempt %s", attempt)
        try:
            page = select_available_site(
                page,
                required_site=settings.observer_required_site,
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
        result = _with_monitor_diagnostics(
            result,
            settings=settings,
            attempt=attempt,
            session_age_seconds=time.monotonic() - session_started,
            check_duration_seconds=time.monotonic() - check_started,
        )

        if result.status == "unavailable":
            reload_started = time.monotonic()
            reload_result = _reload_and_recheck_appointment_availability(
                page,
                settings,
            )
            if reload_result is not None:
                result = _with_monitor_diagnostics(
                    reload_result,
                    settings=settings,
                    attempt=attempt,
                    session_age_seconds=time.monotonic() - session_started,
                    check_duration_seconds=time.monotonic() - reload_started,
                    monitoring_mode="reload_probe",
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

        fetch_probe_only = bool((result.details or {}).get("fetch_probe"))
        can_attempt_reservation = not fetch_probe_only and (
            result.status == "available"
            or (result.status == "partial" and has_available_date_options(page))
        )
        if can_attempt_reservation:
            selected_result = select_available_appointment(
                page,
                is_allowed_appointment=is_allowed_appointment,
                timeout=settings.postback_timeout_seconds * 1_000,
            )
            selected_result = _with_monitor_diagnostics(
                selected_result,
                settings=settings,
                attempt=attempt,
                session_age_seconds=time.monotonic() - session_started,
                check_duration_seconds=time.monotonic() - check_started,
            )
            if not settings.auto_reserve:
                if selected_result.status == "available":
                    if on_check is not None:
                        on_check(selected_result, attempt, None)
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
                        expected_person_name,
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


def _reload_and_recheck_appointment_availability(
    page,
    settings,
) -> AvailabilityResult | None:
    logger.info("No slots detected; reloading page before confirming unavailable result")
    try:
        page.reload(
            wait_until="domcontentloaded",
            timeout=settings.postback_timeout_seconds * 1_000,
        )
        page = click_program_action(page)
        page = open_appointment_panel(page)
        result = read_appointment_availability(
            page,
            timeout=settings.read_timeout_seconds * 1_000,
        )
    except Exception:
        logger.exception("Reload probe failed; keeping the previous unavailable result")
        return None

    if result.status != "unavailable":
        details = dict(result.details or {})
        details["reload_probe"] = True
        return AvailabilityResult(
            status=result.status,
            message=(
                f"{result.message} "
                "La disponibilidad fue detectada despues de recargar la pagina."
            ),
            details=details,
        )

    details = dict(result.details or {})
    details["reload_probe"] = True
    return AvailabilityResult(
        status=result.status,
        message=result.message,
        details=details,
    )


def _with_monitor_diagnostics(
    result: AvailabilityResult,
    *,
    settings: Settings,
    attempt: int,
    session_age_seconds: float,
    check_duration_seconds: float,
    monitoring_mode: str = "normal",
) -> AvailabilityResult:
    details = dict(result.details or {})
    details.update(
        {
            "observer_account": settings.safe_username,
            "observer_attempt": attempt,
            "monitoring_mode": monitoring_mode,
            "session_age_seconds": round(session_age_seconds, 3),
            "check_duration_seconds": round(check_duration_seconds, 3),
        }
    )
    logger.info(
        "Observer check: account=%s mode=%s attempt=%s status=%s site=%s "
        "date_options=%s hour_options=%s duration=%.3fs session_age=%.3fs",
        settings.safe_username,
        monitoring_mode,
        attempt,
        result.status,
        details.get("sede"),
        details.get("date_options"),
        details.get("hour_options"),
        check_duration_seconds,
        session_age_seconds,
    )
    return AvailabilityResult(result.status, result.message, details)


def run_with_report(
    settings: Settings,
    *,
    order_id: str | None = None,
    client_name: str | None = None,
    cancel_event: threading.Event | None = None,
    on_check: Callable[[AvailabilityResult, int, int | None], None] | None = None,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    can_submit: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[dict | None], None] | None = None,
    on_submission_started: Callable[[dict | None], None] | None = None,
    expected_person_name: str | None = None,
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
                    if notify_mode == "full":
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
                        expected_person_name,
                    )
                    result = _with_client_context(
                        result,
                        order_id=order_id,
                        client_name=client_name,
                        settings=settings,
                    )
                    if notify_mode == "full":
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
        if notify_mode == "full":
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
            details={"error_type": type(exc).__name__},
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
        if notify_mode == "full":
            _cleanup_unconfirmed_session_screenshots(finalized_report)
        return finalized_report


def _cleanup_unconfirmed_session_screenshots(report: RunReport) -> None:
    if reservation_confirmed(report) or report.status in {
        "error",
        "unknown",
        "reservation_unconfirmed",
    }:
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
