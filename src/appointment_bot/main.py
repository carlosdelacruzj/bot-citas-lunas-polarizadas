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
    AppointmentOptionsNotRefreshed,
    AppointmentWorkflowCancelled,
    AppointmentWorkflowUnavailable,
    ReservationDeferredForPriority,
    ReservationSubmissionUncertain,
    click_program_action,
    dismiss_reservation_confirmation,
    has_available_date_options,
    open_appointment_panel,
    read_appointment_availability,
    refresh_reservation_captcha,
    select_available_appointment,
    select_available_site,
    solve_reservation_captcha_and_click_reserve,
    validate_selected_appointment,
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
from appointment_bot.services.reservation_timings import (
    ReservationTiming,
    add_reservation_timing_details,
)
from appointment_bot.services.run_reporting import (
    finalize_report,
    report_from_result,
    reservation_confirmed,
)
from appointment_bot.utils.diagnostics import (
    read_visible_page_text,
    save_sanitized_page_html,
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

    label_by_status = {
        "available": "03-modal-reserva-citas-cupo-disponible",
        "partial": "03-modal-reserva-citas-disponibilidad-parcial",
    }
    return save_screenshot(
        page,
        settings,
        label=label_by_status[status],
    )


def _save_process_stages_snapshot(
    page,
    settings,
    *,
    label: str = "02-detalle-tramite-etapas-reservar-cita",
) -> Path | None:
    return save_screenshot(
        page,
        settings,
        label=label,
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
    timing: ReservationTiming | None = None,
    cancel_event: threading.Event | None = None,
    can_submit: Callable[[], bool] | None = None,
    can_solve_captcha: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[dict | None], None] | None = None,
    on_submission_started: Callable[[dict | None], None] | None = None,
    expected_person_name: str | None = None,
) -> tuple[AvailabilityResult, Path | None, list[Path]]:
    submission_started = False
    confirmation_source = "unconfirmed"
    latest_captcha_audit: dict[str, object] = {}
    captcha_attempts: list[dict[str, object]] = []
    diagnostic_artifacts: dict[str, list[str]] = {
        "captcha_images": [],
        "screenshots": [],
        "dom_snapshots": [],
    }
    portal_response: dict[str, object] = {}
    additional_screenshot_paths: list[Path] = []
    max_captcha_attempts = 2

    def add_artifact(kind: str, path: Path | str | None) -> None:
        if path is None:
            return
        value = str(path)
        values = diagnostic_artifacts.setdefault(kind, [])
        if value not in values:
            values.append(value)

    def collected_screenshots(*paths: Path | None) -> list[Path]:
        return [
            path
            for path in [
                *paths,
                *additional_screenshot_paths,
                screenshot_path,
            ]
            if path is not None
        ]

    def reservation_details() -> dict:
        details = add_reservation_timing_details(result.details, timing)
        details.update(latest_captcha_audit)
        if captcha_attempts:
            details["captcha_attempts"] = captcha_attempts
        if portal_response:
            details["portal_response"] = portal_response
        artifacts = {
            key: values
            for key, values in diagnostic_artifacts.items()
            if values
        }
        if artifacts:
            details["diagnostic_artifacts"] = artifacts
        return details

    def mark_submission_started() -> None:
        nonlocal submission_started
        if on_submission_started is not None:
            on_submission_started(result.details)
        submission_started = True

    try:

        def mark_submission_intent() -> None:
            if on_submission_intent is not None:
                on_submission_intent(result.details)

        for captcha_attempt in range(1, max_captcha_attempts + 1):
            attempt_started = time.monotonic()
            captcha_audit: dict[str, object] = {}
            try:
                page = solve_reservation_captcha_and_click_reserve(
                    page,
                    settings,
                    cancel_event=cancel_event,
                    can_submit=can_submit,
                    can_solve_captcha=can_solve_captcha,
                    expected_details=result.details,
                    expected_person_name=expected_person_name,
                    on_submission_intent=mark_submission_intent,
                    on_submission_started=mark_submission_started,
                    captcha_audit=captcha_audit,
                    attempt_number=captcha_attempt,
                    timing=timing,
                )
            except ReservationDeferredForPriority as exc:
                if timing is not None:
                    timing.mark("reservation_finished")
                captcha_audit.update(exc.captcha_audit)
                latest_captcha_audit.clear()
                latest_captcha_audit.update(captcha_audit)
                add_artifact("captcha_images", captcha_audit.get("captcha_image_path"))
                add_artifact("captcha_images", captcha_audit.get("captcha_panel_image_path"))
                captcha_attempts.append(dict(captcha_audit))
                screenshot_candidates = collected_screenshots(
                    Path(str(captcha_audit["captcha_panel_image_path"]))
                    if captcha_audit.get("captcha_panel_image_path")
                    else None,
                    Path(str(captcha_audit["captcha_image_path"]))
                    if captcha_audit.get("captcha_image_path")
                    else None,
                )
                details = reservation_details()
                details["deferred_to_higher_priority"] = True
                details["submission_outcome"] = "priority_deferred"
                return (
                    AvailabilityResult(
                        status="partial",
                        message=str(exc),
                        details=details,
                    ),
                    screenshot_candidates[0] if screenshot_candidates else screenshot_path,
                    screenshot_candidates,
                )
            latest_captcha_audit.clear()
            latest_captcha_audit.update(captcha_audit)
            add_artifact("captcha_images", captcha_audit.get("captcha_image_path"))
            add_artifact("captcha_images", captcha_audit.get("captcha_panel_image_path"))
            pre_submit_path = captcha_audit.get("pre_submit_screenshot_path")
            add_artifact("screenshots", pre_submit_path)
            if pre_submit_path:
                additional_screenshot_paths.append(Path(str(pre_submit_path)))

            submission_outcome = wait_for_reservation_submission_outcome(page)
            confirmation_text_detected = submission_outcome == "confirmed"
            portal_text = read_visible_page_text(page)
            portal_response.clear()
            portal_response.update(
                {
                    "attempt": captcha_attempt,
                    "outcome": submission_outcome,
                    "visible_text": portal_text,
                }
            )
            captcha_audit["submission_outcome"] = submission_outcome
            captcha_audit["duration_seconds"] = round(
                max(time.monotonic() - attempt_started, 0.0),
                3,
            )
            captcha_audit["portal_text"] = portal_text
            reservation_confirmation_screenshot_path = save_screenshot(
                page,
                settings,
                f"06-reserva-respuesta-portal-intento-{captcha_attempt}",
            )
            if reservation_confirmation_screenshot_path is not None:
                captcha_audit["post_submit_screenshot_path"] = str(
                    reservation_confirmation_screenshot_path
                )
                add_artifact("screenshots", reservation_confirmation_screenshot_path)
                additional_screenshot_paths.append(reservation_confirmation_screenshot_path)
            post_submit_html_path = save_sanitized_page_html(
                page,
                settings,
                f"06-reserva-respuesta-portal-html-intento-{captcha_attempt}",
            )
            if post_submit_html_path is not None:
                captcha_audit["post_submit_html_path"] = str(post_submit_html_path)
                add_artifact("dom_snapshots", post_submit_html_path)
            captcha_attempts.append(dict(captcha_audit))
            latest_captcha_audit.clear()
            latest_captcha_audit.update(captcha_audit)
            if timing is not None:
                timing.mark("confirmation_screenshot_saved")

            if confirmation_text_detected:
                if timing is not None:
                    timing.mark("reservation_finished")
                details = reservation_details()
                details["submission_outcome"] = "confirmed"
                details["confirmacion_texto"] = "detectada"
                details["confirmacion_etapa"] = "asumida por mensaje del portal"
                details["confirmation_source"] = "portal_success_text"
                return (
                    AvailabilityResult(
                        status="registered",
                        message="La reserva fue confirmada por mensaje de exito del portal.",
                        details=details,
                    ),
                    reservation_confirmation_screenshot_path or screenshot_path,
                    collected_screenshots(reservation_confirmation_screenshot_path),
                )

            if submission_outcome == "captcha_invalid" and captcha_attempt < max_captcha_attempts:
                dismiss_reservation_confirmation(page)
                refreshed = refresh_reservation_captcha(page, settings)
                captcha_audit["captcha_refreshed_for_retry"] = refreshed
                try:
                    validate_selected_appointment(
                        page,
                        result.details,
                        expected_person_name=expected_person_name,
                    )
                except AppointmentWorkflowUnavailable as exc:
                    if timing is not None:
                        timing.mark("reservation_finished")
                    captcha_audit["retry_aborted_reason"] = str(exc)
                    captcha_attempts[-1] = dict(captcha_audit)
                    latest_captcha_audit.clear()
                    latest_captcha_audit.update(captcha_audit)
                    details = reservation_details()
                    details["submission_outcome"] = "slot_lost"
                    details["captcha_retry_aborted_reason"] = str(exc)
                    return (
                        AvailabilityResult(
                            status="unavailable",
                            message=(
                                "El portal rechazo el captcha y luego el cupo seleccionado "
                                "dejo de estar disponible."
                            ),
                            details=details,
                        ),
                        reservation_confirmation_screenshot_path or screenshot_path,
                        collected_screenshots(reservation_confirmation_screenshot_path),
                    )
                captcha_attempts[-1] = dict(captcha_audit)
                latest_captcha_audit.clear()
                latest_captcha_audit.update(captcha_audit)
                logger.info(
                    "Retrying reservation captcha after invalid captcha response "
                    "(attempt %s of %s)",
                    captcha_attempt + 1,
                    max_captcha_attempts,
                )
                continue

            if submission_outcome != "unknown":
                dismiss_reservation_confirmation(page)
            if submission_outcome in {"captcha_invalid", "slot_lost", "rejected"}:
                if timing is not None:
                    timing.mark("reservation_finished")
                details = reservation_details()
                details["submission_outcome"] = submission_outcome
                messages = {
                    "captcha_invalid": (
                        "El portal rechazo el captcha de la reserva despues "
                        "de reintentarlo."
                    ),
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
                    collected_screenshots(reservation_confirmation_screenshot_path),
                )
            break

        programmed_stage, confirmation_source = _confirm_programmed_stage_after_submission(
            page,
            settings,
            result.details,
            confirmation_text_detected=confirmation_text_detected,
        )
        updated_process_stages_screenshot_path = _save_process_stages_snapshot(
            page,
            settings,
            label="07-detalle-tramite-etapa-programado-confirmada",
        )
        add_artifact("screenshots", updated_process_stages_screenshot_path)
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
    if timing is not None:
        timing.mark("reservation_finished")
    screenshot_paths = collected_screenshots(
        reservation_confirmation_screenshot_path,
        updated_process_stages_screenshot_path,
    )
    if screenshot_paths:
        screenshot_path = screenshot_paths[0]

    details = reservation_details()
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
        message = (
            "El portal mostro mensaje de exito despues de hacer click en Reservar, "
            "pero no se confirmo la etapa Programado."
            if confirmation_text_detected
            else (
                "Se resolvio el captcha y se hizo click en Reservar, "
                "pero no se confirmo la etapa Programado."
            )
        )
        return (
            AvailabilityResult(
                status="reservation_unconfirmed",
                message=message,
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


def _capture_blocked_captcha_evidence(
    page,
    settings,
    result: AvailabilityResult,
    screenshot_path: Path | None,
    timing: ReservationTiming | None = None,
    cancel_event: threading.Event | None = None,
    can_submit: Callable[[], bool] | None = None,
    can_solve_captcha: Callable[[], bool] | None = None,
    expected_person_name: str | None = None,
) -> tuple[AvailabilityResult, Path | None, list[Path]]:
    captcha_audit: dict[str, object] = {}
    deferred_to_higher_priority = (
        can_solve_captcha is not None and not can_solve_captcha()
    )
    try:
        solve_reservation_captcha_and_click_reserve(
            page,
            settings,
            cancel_event=cancel_event,
            can_submit=can_submit,
            can_solve_captcha=lambda: False,
            expected_details=result.details,
            expected_person_name=expected_person_name,
            captcha_audit=captcha_audit,
            attempt_number=1,
            timing=timing,
        )
    except ReservationDeferredForPriority as exc:
        captcha_audit.update(exc.captcha_audit)
    if timing is not None:
        timing.mark("reservation_finished")

    panel_path = (
        Path(str(captcha_audit["captcha_panel_image_path"]))
        if captcha_audit.get("captcha_panel_image_path")
        else None
    )
    captcha_path = (
        Path(str(captcha_audit["captcha_image_path"]))
        if captcha_audit.get("captcha_image_path")
        else None
    )
    screenshot_paths = [
        path for path in [panel_path, captcha_path, screenshot_path] if path is not None
    ]
    details = add_reservation_timing_details(result.details, timing)
    details.update(captcha_audit)
    details["captcha_attempts"] = [dict(captcha_audit)]
    details["submission_outcome"] = (
        "priority_deferred" if deferred_to_higher_priority else "blocked_by_order_rule"
    )
    if deferred_to_higher_priority:
        details["deferred_to_higher_priority"] = True
    captcha_images = [
        str(path)
        for path in [
            captcha_audit.get("captcha_image_path"),
            captcha_audit.get("captcha_panel_image_path"),
        ]
        if path
    ]
    if captcha_images:
        details["diagnostic_artifacts"] = {"captcha_images": captcha_images}
    return (
        AvailabilityResult(
            status="partial",
            message=result.message,
            details=details,
        ),
        screenshot_paths[0] if screenshot_paths else screenshot_path,
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
    can_solve_captcha: Callable[[], bool] | None = None,
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
            if reload_result is None:
                if on_check is not None:
                    on_check(result, attempt, None)
                return result, screenshot_path, screenshot_paths
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
                "03-modal-reserva-citas-resultado-desconocido",
            )
            screenshot_path = result_screenshot_path or process_stages_screenshot_path
            return result, screenshot_path, screenshot_paths

        reservation_timing = (
            ReservationTiming()
            if result.status in {"available", "partial"}
            else None
        )
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
            timing = reservation_timing or ReservationTiming()
            timing.mark("selection_started")
            selected_result = select_available_appointment(
                page,
                is_allowed_appointment=is_allowed_appointment,
                timeout=settings.postback_timeout_seconds * 1_000,
            )
            timing.mark("selection_finished")
            selected_result = _with_monitor_diagnostics(
                selected_result,
                settings=settings,
                attempt=attempt,
                session_age_seconds=time.monotonic() - session_started,
                check_duration_seconds=time.monotonic() - check_started,
            )
            if bool((selected_result.details or {}).get("blocked_selected_for_evidence")):
                if on_check is not None:
                    on_check(selected_result, attempt, None)
                captured_result, screenshot_path, screenshot_paths = (
                    _capture_blocked_captcha_evidence(
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
                )
                if on_check is not None:
                    on_check(captured_result, attempt, None)
                return captured_result, screenshot_path, screenshot_paths
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
                        timing,
                        cancel_event,
                        can_submit,
                        can_solve_captcha,
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
                        can_solve_captcha,
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
                screenshot_path = save_error_screenshot(page, settings, "error-flujo-principal")
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
    details = report.details or {}
    artifacts = details.get("diagnostic_artifacts")
    if details.get("captcha_attempts") or (
        isinstance(artifacts, dict) and artifacts.get("captcha_images")
    ):
        return
    if report.status == "partial" and _has_partial_availability_evidence(details):
        return

    remove_screenshot_paths(report_screenshot_paths(report))


def _has_partial_availability_evidence(details: dict) -> bool:
    date_text = str(details.get("fecha") or details.get("appointment_date") or "").strip()
    hour_text = str(details.get("hora") or details.get("appointment_hour") or "").strip()
    if bool(details.get("blocked_by_order_rule")) or bool(
        details.get("blocked_selected_for_evidence")
    ):
        return True
    if date_text and date_text.casefold() != "sin cupos":
        return True
    return bool(hour_text and hour_text.casefold() != "sin cupos")


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
