from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.core.models import AvailabilityResult
from appointment_bot.reservation_engine.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    AppointmentOptionsNotRefreshed,
    AppointmentWorkflowCancelled,
    has_available_date_options,
    open_appointment_panel,
    read_appointment_availability,
    select_available_appointment,
    select_available_site,
)
from appointment_bot.reservation_engine.programs import click_program_action
from appointment_bot.reservation_engine.reservation_captcha_refresh import (
    ensure_reservation_captcha_loaded,
)
from appointment_bot.reservation_engine.reservation_flow import (
    capture_blocked_captcha_evidence,
    complete_available_reservation,
)
from appointment_bot.reservation_engine.timings import ReservationTiming
from appointment_bot.utils.screenshots import (
    save_centered_modal_screenshot,
    save_result_screenshot,
    save_revealed_centered_modal_screenshot,
    save_screenshot,
)

logger = logging.getLogger(__name__)


@dataclass
class ReservationAttemptOutcome:
    completed_result: tuple[AvailabilityResult, Path | None, list[Path]] | None = None
    selected_result: AvailabilityResult | None = None


def monitor_appointment_availability(
    page,
    settings: Settings,
    process_stages_screenshot_path: Path | None,
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
    run_id: str | None = None,
    order_id: str | None = None,
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
        result = with_monitor_diagnostics(
            result,
            settings=settings,
            attempt=attempt,
            session_age_seconds=time.monotonic() - session_started,
            check_duration_seconds=time.monotonic() - check_started,
        )

        if result.status == "unavailable":
            reload_started = time.monotonic()
            reload_result = reload_and_recheck_appointment_availability(
                page,
                settings,
                program_expediente=program_expediente,
                program_plate=program_plate,
            )
            if reload_result is None:
                if on_check is not None:
                    on_check(result, attempt, None)
                return result, screenshot_path, screenshot_paths
            result = with_monitor_diagnostics(
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
                "03-modal-reserva-citas-resultado-desconocido",
            )
            screenshot_path = result_screenshot_path or process_stages_screenshot_path
            return result, screenshot_path, screenshot_paths

        reservation_timing = (
            ReservationTiming() if result.status in {"available", "partial"} else None
        )
        result_screenshot_path = save_relevant_result_snapshot(page, settings, result.status)
        screenshot_path = result_screenshot_path or process_stages_screenshot_path

        fetch_probe_only = bool((result.details or {}).get("fetch_probe"))
        can_attempt_reservation = not fetch_probe_only and (
            result.status == "available"
            or (result.status == "partial" and has_available_date_options(page))
        )
        if can_attempt_reservation:
            reservation_outcome = _try_reservation_from_availability(
                page,
                settings,
                result,
                attempt,
                session_started,
                check_started,
                screenshot_path,
                screenshot_paths,
                reservation_timing,
                cancel_event,
                on_check,
                is_allowed_appointment,
                can_submit,
                can_solve_captcha,
                on_submission_intent,
                on_submission_started,
                expected_person_name,
                run_id,
                order_id,
            )
            if reservation_outcome.completed_result is not None:
                return reservation_outcome.completed_result
            if reservation_outcome.selected_result is not None:
                result = reservation_outcome.selected_result

        # Una disponibilidad parcial tambien se vuelve a comprobar dentro
        # de la misma sesion; una fecha puede cargar sus horas en un intento posterior.
        if result.status not in {"unavailable", "partial"}:
            if on_check is not None:
                on_check(result, attempt, None)
            return result, screenshot_path, screenshot_paths

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


def _try_reservation_from_availability(
    page,
    settings: Settings,
    result: AvailabilityResult,
    attempt: int,
    session_started: float,
    check_started: float,
    screenshot_path: Path | None,
    screenshot_paths: list[Path],
    reservation_timing: ReservationTiming | None,
    cancel_event: threading.Event | None,
    on_check: Callable[[AvailabilityResult, int, int | None], None] | None,
    is_allowed_appointment: Callable[[str, str], bool] | None,
    can_submit: Callable[[], bool] | None,
    can_solve_captcha: Callable[[], bool] | None,
    on_submission_intent: Callable[[dict | None], None] | None,
    on_submission_started: Callable[[dict | None], None] | None,
    expected_person_name: str | None,
    run_id: str | None,
    order_id: str | None,
):
    timing = reservation_timing or ReservationTiming()
    timing.mark("selection_started")
    selected_result = select_available_appointment(
        page,
        is_allowed_appointment=is_allowed_appointment,
        timeout=settings.postback_timeout_seconds * 1_000,
    )
    timing.mark("selection_finished")
    selected_result = with_monitor_diagnostics(
        selected_result,
        settings=settings,
        attempt=attempt,
        session_age_seconds=time.monotonic() - session_started,
        check_duration_seconds=time.monotonic() - check_started,
    )
    if selected_result.status == "available":
        selected_screenshot_path = save_available_appointment_snapshot(page, settings)
        if selected_screenshot_path is not None:
            screenshot_path = selected_screenshot_path
    if bool((selected_result.details or {}).get("blocked_selected_for_evidence")):
        if on_check is not None:
            on_check(selected_result, attempt, None)
        captured_result, screenshot_path, screenshot_paths = capture_blocked_captcha_evidence(
            page,
            settings,
            selected_result,
            screenshot_path,
            timing,
            cancel_event,
            can_submit,
            can_solve_captcha,
            expected_person_name,
        )
        if on_check is not None:
            on_check(captured_result, attempt, None)
        return ReservationAttemptOutcome(
            completed_result=(captured_result, screenshot_path, screenshot_paths),
            selected_result=selected_result,
        )
    if not settings.auto_reserve:
        if selected_result.status == "available":
            if on_check is not None:
                on_check(selected_result, attempt, None)
            return ReservationAttemptOutcome(
                completed_result=(
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
                ),
                selected_result=selected_result,
            )
        return ReservationAttemptOutcome(selected_result=selected_result)
    if selected_result.status == "available":
        if cancel_event is not None and cancel_event.is_set():
            return ReservationAttemptOutcome(
                completed_result=(
                    AvailabilityResult(
                        status="paused",
                        message=("La pausa se aplico antes de iniciar la reserva."),
                    ),
                    screenshot_path,
                    screenshot_paths,
                ),
                selected_result=selected_result,
            )
        if on_check is not None:
            on_check(selected_result, attempt, None)
        try:
            return ReservationAttemptOutcome(
                completed_result=complete_available_reservation(
                    page,
                    settings,
                    selected_result,
                    screenshot_path,
                    timing,
                    cancel_event,
                    can_submit,
                    can_solve_captcha,
                    on_submission_intent,
                    on_submission_started,
                    expected_person_name,
                    run_id=run_id,
                    order_id=order_id,
                ),
                selected_result=selected_result,
            )
        except AppointmentWorkflowCancelled as exc:
            return ReservationAttemptOutcome(
                completed_result=(
                    AvailabilityResult(status="paused", message=str(exc)),
                    screenshot_path,
                    screenshot_paths,
                ),
                selected_result=selected_result,
            )
    return ReservationAttemptOutcome(selected_result=selected_result)


def reload_and_recheck_appointment_availability(
    page,
    settings: Settings,
    *,
    program_expediente: str | None = None,
    program_plate: str | None = None,
) -> AvailabilityResult | None:
    logger.info("No slots detected; reloading page before confirming unavailable result")
    try:
        page.reload(
            wait_until="domcontentloaded",
            timeout=settings.postback_timeout_seconds * 1_000,
        )
        page = click_program_action(
            page,
            program_expediente=program_expediente,
            program_plate=program_plate,
        )
        page = open_appointment_panel(page)
        page = select_available_site(
            page,
            required_site=settings.observer_required_site,
            timeout=settings.postback_timeout_seconds * 1_000,
        )
        result = read_appointment_availability(
            page,
            timeout=settings.read_timeout_seconds * 1_000,
        )
    except Exception:
        logger.exception("Reload probe failed; keeping the previous unavailable result")
        return None

    details = dict(result.details or {})
    details["reload_probe"] = True
    message = result.message
    if result.status != "unavailable":
        message = (
            f"{result.message} "
            "La disponibilidad fue detectada despues de recargar la pagina."
        )
    return AvailabilityResult(status=result.status, message=message, details=details)


def with_monitor_diagnostics(
    result: AvailabilityResult,
    *,
    settings: Settings,
    attempt: int,
    session_age_seconds: float,
    check_duration_seconds: float,
    monitoring_mode: str = "normal",
) -> AvailabilityResult:
    details = dict(result.details or {})
    detection_origin = (
        "fetch_probe"
        if details.get("fetch_probe")
        else ("reload_probe" if monitoring_mode == "reload_probe" else "normal")
    )
    details.update(
        {
            "observer_account": settings.safe_username,
            "observer_attempt": attempt,
            "monitoring_mode": monitoring_mode,
            "detection_origin": detection_origin,
            "session_age_seconds": round(session_age_seconds, 3),
            "check_duration_seconds": round(check_duration_seconds, 3),
        }
    )
    logger.info(
        "Observer check: account=%s mode=%s attempt=%s status=%s site=%s "
        "date_options=%s hour_options=%s origin=%s refresh_confirmed=%s "
        "refresh_changed=%s duration=%.3fs session_age=%.3fs",
        settings.safe_username,
        monitoring_mode,
        attempt,
        result.status,
        details.get("sede"),
        details.get("date_options"),
        details.get("hour_options"),
        detection_origin,
        details.get("site_refresh_confirmed"),
        details.get("site_refresh_changed"),
        check_duration_seconds,
        session_age_seconds,
    )
    return AvailabilityResult(result.status, result.message, details)


def save_relevant_result_snapshot(page, settings: Settings, status: str) -> Path | None:
    if status != "partial":
        return None

    label_by_status = {
        "partial": "03-modal-reserva-citas-disponibilidad-parcial",
    }
    centered_path = save_centered_modal_screenshot(
        page,
        settings,
        label=label_by_status[status],
        selectors=APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    )
    if centered_path is not None:
        return centered_path

    return save_screenshot(page, settings, label=label_by_status[status])


def save_available_appointment_snapshot(page, settings: Settings) -> Path | None:
    return save_revealed_centered_modal_screenshot(
        page,
        settings,
        "03-modal-reserva-citas-cupo-disponible",
        APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
        ready_check=lambda panel: ensure_reservation_captcha_loaded(
            panel,
            timeout=settings.read_timeout_seconds * 1_000,
        ),
    )
