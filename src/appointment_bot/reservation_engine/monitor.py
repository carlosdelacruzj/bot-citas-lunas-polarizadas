from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError

from appointment_bot.config import Settings
from appointment_bot.core.models import AvailabilityResult
from appointment_bot.reservation_engine.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    AppointmentOptionsNotRefreshed,
    AppointmentWorkflowCancelled,
    AppointmentWorkflowUnavailable,
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

_OPPORTUNITY_EXECUTION_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar(
    "opportunity_execution_context",
    default=None,
)


def set_opportunity_execution_context(
    context: dict[str, str] | None,
) -> Token[dict[str, str] | None]:
    return _OPPORTUNITY_EXECUTION_CONTEXT.set(context)


def reset_opportunity_execution_context(
    token: Token[dict[str, str] | None],
) -> None:
    _OPPORTUNITY_EXECUTION_CONTEXT.reset(token)


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
    on_submission_resolved: Callable[[str, str | None, str | None], None] | None = None,
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
    site_refresh_history: list[dict] = []

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
        site_toggle_probe = settings.monitor_site_toggle_enabled and attempt > 1
        try:
            page = select_available_site(
                page,
                required_site=settings.observer_required_site,
                reset_first=site_toggle_probe,
                timeout=settings.postback_timeout_seconds * 1_000,
                telemetry_attempt=attempt,
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
        result, site_refresh_history = _with_accumulated_site_refresh_history(
            result,
            site_refresh_history,
        )
        result = with_monitor_diagnostics(
            result,
            settings=settings,
            attempt=attempt,
            session_age_seconds=time.monotonic() - session_started,
            check_duration_seconds=time.monotonic() - check_started,
            monitoring_mode="site_toggle" if site_toggle_probe else "normal",
        )

        should_reload_probe = (
            not settings.monitor_site_toggle_enabled
            or attempt == settings.monitor_reload_probe_after_attempt
        )
        if result.status == "unavailable" and should_reload_probe:
            reload_started = time.monotonic()
            reload_result = reload_and_recheck_appointment_availability(
                page,
                settings,
                program_expediente=program_expediente,
                program_plate=program_plate,
                telemetry_attempt=attempt,
            )
            if reload_result is None:
                if settings.monitor_site_toggle_enabled:
                    logger.warning(
                        "Scheduled reload probe failed; continuing the light site probes"
                    )
                else:
                    if on_check is not None:
                        on_check(result, attempt, None)
                    return result, screenshot_path, screenshot_paths
            else:
                reload_result, site_refresh_history = _with_accumulated_site_refresh_history(
                    reload_result,
                    site_refresh_history,
                )
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
                on_submission_resolved,
                expected_person_name,
                program_expediente,
                program_plate,
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
    on_submission_resolved: Callable[[str, str | None, str | None], None] | None,
    expected_person_name: str | None,
    program_expediente: str | None,
    program_plate: str | None,
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
            run_id=run_id,
            order_id=order_id,
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
            completed_result = complete_available_reservation(
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
            )
            if not _is_explicit_slot_lost(completed_result[0]) or not (
                settings.slot_lost_reobservation_enabled
            ):
                return ReservationAttemptOutcome(
                    completed_result=completed_result,
                    selected_result=selected_result,
                )
            if not _reobservation_admission_allowed(settings):
                return ReservationAttemptOutcome(
                    completed_result=completed_result,
                    selected_result=selected_result,
                )
            if on_submission_resolved is not None:
                on_submission_resolved(
                    "slot_lost",
                    run_id,
                    str(completed_result[1]) if completed_result[1] is not None else None,
                )
            return ReservationAttemptOutcome(
                completed_result=_reobserve_after_slot_lost(
                    page,
                    settings,
                    completed_result,
                    original_attempt=attempt,
                    session_started=session_started,
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


def _is_explicit_slot_lost(result: AvailabilityResult) -> bool:
    return (
        result.status == "unavailable"
        and str((result.details or {}).get("submission_outcome") or "") == "slot_lost"
    )


def _reobserve_after_slot_lost(
    page,
    settings: Settings,
    original_completed_result: tuple[AvailabilityResult, Path | None, list[Path]],
    *,
    original_attempt: int,
    session_started: float,
    cancel_event: threading.Event | None,
    on_check: Callable[[AvailabilityResult, int, int | None], None] | None,
    is_allowed_appointment: Callable[[str, str], bool] | None,
    can_submit: Callable[[], bool] | None,
    can_solve_captcha: Callable[[], bool] | None,
    on_submission_intent: Callable[[dict | None], None] | None,
    on_submission_started: Callable[[dict | None], None] | None,
    expected_person_name: str | None,
    program_expediente: str | None,
    program_plate: str | None,
    run_id: str | None,
    order_id: str | None,
) -> tuple[AvailabilityResult, Path | None, list[Path]]:
    _, original_screenshot_path, _ = original_completed_result
    reobservation_id = f"reobservation-{uuid4().hex}"
    started_at = time.monotonic()
    deadline = started_at + settings.slot_lost_reobservation_seconds
    observations: list[dict] = []
    reload_probe_used = False
    if not _record_reobservation_event(
        reobservation_id,
        0,
        "slot_lost_resolved",
        order_id=order_id,
        run_id=run_id,
        outcome="slot_lost",
        settings=settings,
    ):
        return original_completed_result
    if not _record_reobservation_event(
        reobservation_id,
        1,
        "started",
        order_id=order_id,
        run_id=run_id,
        details={
            "max_seconds": settings.slot_lost_reobservation_seconds,
            "max_attempts": settings.slot_lost_reobservation_attempts,
        },
        settings=settings,
    ):
        return original_completed_result

    logger.info(
        "Starting slot_lost reobservation for up to %s seconds and %s attempts",
        settings.slot_lost_reobservation_seconds,
        settings.slot_lost_reobservation_attempts,
    )
    if not _appointment_panel_is_visible(page):
        try:
            page = open_appointment_panel(page)
        except AppointmentWorkflowUnavailable as exc:
            observations.append(
                {
                    "attempt": 0,
                    "mode": "panel_reopen",
                    "status": "panel_unavailable",
                    "message": str(exc),
                    "duration_seconds": round(time.monotonic() - started_at, 3),
                }
            )
            return _finish_slot_lost_reobservation(
                original_completed_result,
                settings,
                observations,
                started_at,
                reload_probe_used,
                reobservation_id=reobservation_id,
                outcome="panel_unavailable",
            )

    for reobservation_attempt in range(1, settings.slot_lost_reobservation_attempts + 1):
        if cancel_event is not None and cancel_event.is_set():
            return _finish_slot_lost_reobservation(
                original_completed_result,
                settings,
                observations,
                started_at,
                reload_probe_used,
                reobservation_id=reobservation_id,
                outcome="paused",
                message="La reobservacion posterior a slot_lost fue interrumpida por una pausa.",
                status="paused",
            )
        if time.monotonic() >= deadline:
            break

        check_started = time.monotonic()
        use_reload_probe = (
            reobservation_attempt
            == settings.slot_lost_reobservation_reload_probe_after_attempt
        )
        if use_reload_probe:
            reload_probe_used = True
            result = reload_and_recheck_appointment_availability(
                page,
                settings,
                program_expediente=program_expediente,
                program_plate=program_plate,
                telemetry_attempt=reobservation_attempt,
            )
            if result is None:
                observations.append(
                    {
                        "attempt": reobservation_attempt,
                        "mode": "reload_probe",
                        "status": "reload_failed",
                        "duration_seconds": round(time.monotonic() - check_started, 3),
                    }
                )
                break
            monitoring_mode = "reload_probe"
        else:
            page = select_available_site(
                page,
                required_site=settings.observer_required_site,
                reset_first=True,
                timeout=settings.postback_timeout_seconds * 1_000,
                telemetry_attempt=reobservation_attempt,
                telemetry_phase="slot_lost_reobservation",
            )
            result = read_appointment_availability(
                page,
                timeout=settings.read_timeout_seconds * 1_000,
            )
            monitoring_mode = "slot_lost_reobservation"

        result = with_monitor_diagnostics(
            result,
            settings=settings,
            attempt=original_attempt + reobservation_attempt,
            session_age_seconds=time.monotonic() - session_started,
            check_duration_seconds=time.monotonic() - check_started,
            monitoring_mode=monitoring_mode,
        )
        observation = {
            "attempt": reobservation_attempt,
            "mode": monitoring_mode,
            "status": result.status,
            "duration_seconds": round(time.monotonic() - check_started, 3),
        }
        observations.append(observation)
        event_recorded = _record_reobservation_event(
            reobservation_id,
            len(observations) + 1,
            "observation",
            order_id=order_id,
            run_id=run_id,
            attempt_number=reobservation_attempt,
            mode=monitoring_mode,
            observed_status=result.status,
            duration_ms=int((time.monotonic() - check_started) * 1000),
            details=observation,
            settings=settings,
        )
        if not event_recorded:
            return _finish_slot_lost_reobservation(
                original_completed_result,
                settings,
                observations,
                started_at,
                reload_probe_used,
                reobservation_id=reobservation_id,
                outcome="telemetry_failed",
            )
        if on_check is not None:
            on_check(result, original_attempt + reobservation_attempt, None)

        can_select = result.status == "available" or (
            result.status == "partial" and has_available_date_options(page)
        )
        if can_select:
            timing = ReservationTiming()
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
                attempt=original_attempt + reobservation_attempt,
                session_age_seconds=time.monotonic() - session_started,
                check_duration_seconds=time.monotonic() - check_started,
                monitoring_mode=monitoring_mode,
            )
            observation["selected_status"] = selected_result.status
            if selected_result.status == "available":
                recovered_screenshot_path = save_available_appointment_snapshot(page, settings)
                if on_check is not None:
                    on_check(
                        selected_result,
                        original_attempt + reobservation_attempt,
                        None,
                    )

                def record_second_submission_intent(details: dict | None) -> None:
                    if on_submission_intent is not None:
                        on_submission_intent(details)
                    if not _record_reobservation_event(
                        reobservation_id,
                        len(observations) + 2,
                        "second_attempt_intent",
                        order_id=order_id,
                        run_id=run_id,
                        outcome="intent",
                        settings=settings,
                    ):
                        raise RuntimeError(
                            "Could not persist the second reservation attempt intent."
                        )

                recovered_completed_result = complete_available_reservation(
                    page,
                    settings,
                    selected_result,
                    recovered_screenshot_path or original_screenshot_path,
                    timing,
                    cancel_event,
                    can_submit,
                    can_solve_captcha,
                    record_second_submission_intent,
                    on_submission_started,
                    expected_person_name,
                    run_id=run_id,
                    order_id=order_id,
                )
                return _merge_recovered_reservation(
                    original_completed_result,
                    settings,
                    recovered_completed_result,
                    observations,
                    started_at,
                    reload_probe_used,
                    reobservation_id=reobservation_id,
                )

        if result.status == "unknown":
            break
        if reobservation_attempt >= settings.slot_lost_reobservation_attempts:
            break
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            break
        wait_seconds = min(
            random.randint(
                settings.observer_site_toggle_interval_min_seconds,
                settings.observer_site_toggle_interval_max_seconds,
            ),
            max(1, int(remaining_seconds)),
        )
        if cancel_event is not None:
            if cancel_event.wait(wait_seconds):
                return _finish_slot_lost_reobservation(
                    original_completed_result,
                    settings,
                    observations,
                    started_at,
                    reload_probe_used,
                    reobservation_id=reobservation_id,
                    outcome="paused",
                    message=(
                        "La reobservacion posterior a slot_lost fue interrumpida por una pausa."
                    ),
                    status="paused",
                )
        else:
            page.wait_for_timeout(wait_seconds * 1_000)

    return _finish_slot_lost_reobservation(
        original_completed_result,
        settings,
        observations,
        started_at,
        reload_probe_used,
        reobservation_id=reobservation_id,
        outcome="exhausted",
    )


def _finish_slot_lost_reobservation(
    original_completed_result: tuple[AvailabilityResult, Path | None, list[Path]],
    settings: Settings,
    observations: list[dict],
    started_at: float,
    reload_probe_used: bool,
    *,
    reobservation_id: str,
    outcome: str,
    message: str | None = None,
    status: str | None = None,
) -> tuple[AvailabilityResult, Path | None, list[Path]]:
    result, screenshot_path, screenshot_paths = original_completed_result
    details = dict(result.details or {})
    details["slot_lost_reobservation"] = _slot_lost_reobservation_details(
        observations,
        started_at,
        reload_probe_used,
        max_seconds=settings.slot_lost_reobservation_seconds,
        max_attempts=settings.slot_lost_reobservation_attempts,
        outcome=outcome,
        recovered=False,
    )
    _record_reobservation_event(
        reobservation_id,
        len(observations) + 2,
        "finished",
        outcome=outcome,
        observed_status=status or result.status,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        details=details["slot_lost_reobservation"],
        settings=settings,
    )
    return (
        AvailabilityResult(
            status=status or result.status,
            message=message or result.message,
            details=details,
        ),
        screenshot_path,
        screenshot_paths,
    )


def _merge_recovered_reservation(
    original_completed_result: tuple[AvailabilityResult, Path | None, list[Path]],
    settings: Settings,
    recovered_completed_result: tuple[AvailabilityResult, Path | None, list[Path]],
    observations: list[dict],
    started_at: float,
    reload_probe_used: bool,
    *,
    reobservation_id: str,
) -> tuple[AvailabilityResult, Path | None, list[Path]]:
    original_result, original_screenshot_path, original_screenshot_paths = (
        original_completed_result
    )
    recovered_result, recovered_screenshot_path, recovered_screenshot_paths = (
        recovered_completed_result
    )
    details = dict(recovered_result.details or {})
    details["slot_lost_reobservation"] = _slot_lost_reobservation_details(
        observations,
        started_at,
        reload_probe_used,
        max_seconds=settings.slot_lost_reobservation_seconds,
        max_attempts=settings.slot_lost_reobservation_attempts,
        outcome="reservation_attempted",
        recovered=True,
    )
    details["previous_submission_outcomes"] = [
        {
            "outcome": "slot_lost",
            "sede": (original_result.details or {}).get("sede"),
            "fecha": (original_result.details or {}).get("fecha"),
            "hora": (original_result.details or {}).get("hora"),
            "reservation_timing": (original_result.details or {}).get(
                "reservation_timing"
            ),
        }
    ]
    _record_reobservation_event(
        reobservation_id,
        len(observations) + 3,
        "second_attempt_resolved",
        outcome=str((recovered_result.details or {}).get("submission_outcome") or ""),
        observed_status=recovered_result.status,
        settings=settings,
    )
    _record_reobservation_event(
        reobservation_id,
        len(observations) + 4,
        "finished",
        outcome="reservation_attempted",
        observed_status=recovered_result.status,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        details=details["slot_lost_reobservation"],
        settings=settings,
    )
    screenshot_paths = _unique_paths(
        original_screenshot_paths,
        [original_screenshot_path] if original_screenshot_path is not None else [],
        recovered_screenshot_paths,
        [recovered_screenshot_path] if recovered_screenshot_path is not None else [],
    )
    return (
        AvailabilityResult(
            status=recovered_result.status,
            message=recovered_result.message,
            details=details,
        ),
        recovered_screenshot_path or original_screenshot_path,
        screenshot_paths,
    )


def _slot_lost_reobservation_details(
    observations: list[dict],
    started_at: float,
    reload_probe_used: bool,
    *,
    max_seconds: int,
    max_attempts: int,
    outcome: str,
    recovered: bool,
) -> dict:
    return {
        "enabled": True,
        "max_seconds": max_seconds,
        "max_attempts": max_attempts,
        "attempts_completed": len(observations),
        "reload_probe_used": reload_probe_used,
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
        "outcome": outcome,
        "recovered_availability": recovered,
        "observations": observations,
    }


def _reobservation_admission_allowed(settings: Settings) -> bool:
    try:
        from appointment_bot.db.opportunity_controls import (
            is_opportunity_admission_allowed,
        )

        return bool(is_opportunity_admission_allowed("obs007", settings=settings))
    except Exception:
        logger.exception("Could not read OBS-007 admission control")
        _trip_opportunity_breaker("persistence_failed", None, settings)
        return False


def _record_reobservation_event(
    reobservation_id: str,
    sequence: int,
    event_type: str,
    *,
    order_id: str | None = None,
    run_id: str | None = None,
    attempt_number: int | None = None,
    mode: str | None = None,
    observed_status: str | None = None,
    outcome: str | None = None,
    duration_ms: int | None = None,
    details: dict | None = None,
    settings: Settings,
) -> bool:
    context = _OPPORTUNITY_EXECUTION_CONTEXT.get() or {}
    burst_id = context.get("burst_id")
    execution_id = context.get("execution_id")
    try:
        from appointment_bot.db.opportunity_bursts import record_burst_event

        record_burst_event(
            reobservation_id=reobservation_id,
            sequence=sequence,
            event_type=event_type,
            burst_id=burst_id,
            execution_id=execution_id,
            order_id=order_id,
            run_id=run_id,
            original_attempt_id=context.get("original_attempt_id"),
            second_attempt_id=context.get("second_attempt_id"),
            attempt_number=attempt_number,
            mode=mode,
            observed_status=observed_status,
            outcome=outcome,
            duration_ms=duration_ms,
            details=details,
            event_key=f"{reobservation_id}:{sequence}:{event_type}",
            settings=settings,
        )
        return True
    except Exception:
        logger.exception("Could not persist OBS-007 event %s", event_type)
        _trip_opportunity_breaker("persistence_failed", burst_id, settings)
        return False


def _trip_opportunity_breaker(
    reason: str,
    burst_id: str | None,
    settings: Settings,
) -> None:
    try:
        from appointment_bot.db.opportunity_controls import (
            trip_opportunity_circuit_breaker,
        )

        trip_opportunity_circuit_breaker(
            reason=reason,
            burst_id=burst_id,
            settings=settings,
        )
    except Exception:
        logger.exception("Could not trip opportunity circuit breaker: %s", reason)


def _unique_paths(*groups: list[Path]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for group in groups:
        for path in group:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
    return paths


def _appointment_panel_is_visible(page) -> bool:
    try:
        site = page.locator("#MainContent_idUcitas_cbosede").first
        return site.count() > 0 and site.is_visible(timeout=500)
    except PlaywrightError:
        return False


def reload_and_recheck_appointment_availability(
    page,
    settings: Settings,
    *,
    program_expediente: str | None = None,
    program_plate: str | None = None,
    telemetry_attempt: int | None = None,
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
            telemetry_attempt=telemetry_attempt,
            telemetry_phase="reload_required_site",
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


def _with_accumulated_site_refresh_history(
    result: AvailabilityResult,
    accumulated: list[dict],
) -> tuple[AvailabilityResult, list[dict]]:
    details = dict(result.details or {})
    merged = list(accumulated)
    known_event_ids = {
        str(item.get("event_id"))
        for item in merged
        if isinstance(item, dict) and item.get("event_id")
    }
    for item in details.get("site_refresh_history") or []:
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("event_id") or "")
        if event_id and event_id in known_event_ids:
            continue
        merged.append(dict(item))
        if event_id:
            known_event_ids.add(event_id)
    details["site_refresh_history"] = merged
    details["site_refresh_event_count"] = len(merged)
    return AvailabilityResult(result.status, result.message, details), merged


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
        else (
            monitoring_mode
            if monitoring_mode
            in {"reload_probe", "site_toggle", "slot_lost_reobservation"}
            else "normal"
        )
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
        "refresh_changed=%s post=%s http=%s refresh_events=%s "
        "duration=%.3fs session_age=%.3fs",
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
        details.get("site_refresh_post_detected"),
        details.get("site_refresh_post_status"),
        details.get("site_refresh_event_count"),
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
