from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult
from appointment_bot.reservation_engine.appointments import (
    AppointmentWorkflowUnavailable,
    ReservationDeferredForPriority,
    ReservationSubmissionUncertain,
    validate_selected_appointment,
)
from appointment_bot.reservation_engine.reservation_captcha_refresh import (
    refresh_reservation_captcha,
)
from appointment_bot.reservation_engine.reservation_portal import (
    dismiss_reservation_confirmation,
    wait_for_reservation_submission_outcome,
)
from appointment_bot.reservation_engine.reservation_submit import (
    solve_reservation_captcha_and_click_reserve,
)
from appointment_bot.reservation_engine.stages import wait_for_programmed_appointment_stage
from appointment_bot.reservation_engine.timings import (
    ReservationTiming,
    add_reservation_timing_details,
)
from appointment_bot.utils.diagnostics import (
    read_visible_page_text,
    save_sanitized_page_html,
)
from appointment_bot.utils.screenshots import save_screenshot

logger = logging.getLogger(__name__)


def _add_diagnostic_artifact(
    diagnostic_artifacts: dict[str, list[str]],
    kind: str,
    path: Path | str | None,
) -> None:
    if path is None:
        return
    value = str(path)
    values = diagnostic_artifacts.setdefault(kind, [])
    if value not in values:
        values.append(value)


def _collect_screenshots(
    additional_screenshot_paths: list[Path],
    primary_screenshot_path: Path | None,
    *paths: Path | None,
) -> list[Path]:
    return [
        path
        for path in [
            *paths,
            *additional_screenshot_paths,
            primary_screenshot_path,
        ]
        if path is not None
    ]


def _build_reservation_details(
    result: AvailabilityResult,
    timing: ReservationTiming | None,
    latest_captcha_audit: dict[str, object],
    captcha_attempts: list[dict[str, object]],
    portal_response: dict[str, object],
    diagnostic_artifacts: dict[str, list[str]],
) -> dict:
    details = add_reservation_timing_details(result.details, timing)
    details.update(latest_captcha_audit)
    if captcha_attempts:
        details["captcha_attempts"] = captcha_attempts
    if portal_response:
        details["portal_response"] = portal_response
    artifacts = {key: values for key, values in diagnostic_artifacts.items() if values}
    if artifacts:
        details["diagnostic_artifacts"] = artifacts
    return details


def complete_available_reservation(
    page,
    settings: Settings,
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

    def collected_screenshots(*paths: Path | None) -> list[Path]:
        return _collect_screenshots(additional_screenshot_paths, screenshot_path, *paths)

    def reservation_details() -> dict:
        return _build_reservation_details(
            result,
            timing,
            latest_captcha_audit,
            captcha_attempts,
            portal_response,
            diagnostic_artifacts,
        )

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
                _add_diagnostic_artifact(
                    diagnostic_artifacts,
                    "captcha_images",
                    captcha_audit.get("captcha_image_path"),
                )
                _add_diagnostic_artifact(
                    diagnostic_artifacts,
                    "captcha_images",
                    captcha_audit.get("captcha_screenshot_image_path"),
                )
                captcha_attempts.append(dict(captcha_audit))
                screenshot_candidates = collected_screenshots(
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
            _add_diagnostic_artifact(
                diagnostic_artifacts,
                "captcha_images",
                captcha_audit.get("captcha_image_path"),
            )
            _add_diagnostic_artifact(
                diagnostic_artifacts,
                "captcha_images",
                captcha_audit.get("captcha_screenshot_image_path"),
            )
            pre_submit_path = captcha_audit.get("pre_submit_screenshot_path")
            _add_diagnostic_artifact(diagnostic_artifacts, "screenshots", pre_submit_path)
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
                _add_diagnostic_artifact(
                    diagnostic_artifacts,
                    "screenshots",
                    reservation_confirmation_screenshot_path,
                )
                additional_screenshot_paths.append(reservation_confirmation_screenshot_path)
            post_submit_html_path = save_sanitized_page_html(
                page,
                settings,
                f"06-reserva-respuesta-portal-html-intento-{captcha_attempt}",
            )
            if post_submit_html_path is not None:
                captcha_audit["post_submit_html_path"] = str(post_submit_html_path)
                _add_diagnostic_artifact(
                    diagnostic_artifacts,
                    "dom_snapshots",
                    post_submit_html_path,
                )
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
            result.details,
            confirmation_text_detected=confirmation_text_detected,
        )
        updated_process_stages_screenshot_path = _save_process_stages_snapshot(
            page,
            settings,
            label="07-detalle-tramite-etapa-programado-confirmada",
        )
        _add_diagnostic_artifact(
            diagnostic_artifacts,
            "screenshots",
            updated_process_stages_screenshot_path,
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


def capture_blocked_captcha_evidence(
    page,
    settings: Settings,
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

    captcha_path = (
        Path(str(captcha_audit["captcha_image_path"]))
        if captcha_audit.get("captcha_image_path")
        else None
    )
    screenshot_paths = [
        path for path in [captcha_path, screenshot_path] if path is not None
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
            captcha_audit.get("captcha_screenshot_image_path"),
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


def _confirm_programmed_stage_after_submission(
    page,
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


def _save_process_stages_snapshot(
    page,
    settings: Settings,
    *,
    label: str,
) -> Path | None:
    return save_screenshot(page, settings, label=label)
