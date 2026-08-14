from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.config import Settings
from appointment_bot.reservation_engine.appointments import (
    AppointmentWorkflowCancelled,
    ReservationDeferredForPriority,
    ReservationSubmissionUncertain,
    validate_selected_appointment,
)
from appointment_bot.reservation_engine.reservation_captcha_capture import (
    captcha_submission_image_path,
    save_reservation_captcha_image,
)
from appointment_bot.reservation_engine.reservation_captcha_sampling import (
    collect_reservation_captcha_training_samples,
)
from appointment_bot.reservation_engine.reservation_controls import (
    RESERVATION_BUTTON_SELECTOR,
    RESERVATION_FIELD_SELECTOR,
)
from appointment_bot.reservation_engine.timings import ReservationTiming
from appointment_bot.services.captcha import solve_normal_captcha
from appointment_bot.services.captcha_authority import solve_reservation_captcha
from appointment_bot.services.captcha_shadow import (
    enqueue_shadow_external_result,
    enqueue_shadow_prediction,
)

logger = logging.getLogger(__name__)


def _validate_reservation_selection(
    page: Page,
    settings: Settings,
    *,
    expected_details: dict[str, Any] | None,
    expected_person_name: str | None,
    timing: ReservationTiming | None,
    timing_prefix: str,
    captcha_audit: dict[str, Any],
) -> dict[str, Any]:
    if timing is not None:
        timing.mark(f"{timing_prefix}_started")
    try:
        validation = validate_selected_appointment(
            page,
            expected_details,
            expected_person_name=expected_person_name,
            use_atomic_dom=settings.appointment_atomic_validation_enabled,
        )
    finally:
        if timing is not None:
            timing.mark(f"{timing_prefix}_finished")
    audit_entry = {"phase": timing_prefix, **validation}
    captcha_audit.setdefault("selection_validation_audits", []).append(audit_entry)
    return audit_entry


def solve_reservation_captcha_and_click_reserve(
    page: Page,
    settings: Settings,
    *,
    cancel_event: threading.Event | None = None,
    can_submit: Callable[[], bool] | None = None,
    can_solve_captcha: Callable[[], bool] | None = None,
    expected_details: dict[str, Any] | None = None,
    expected_person_name: str | None = None,
    on_submission_intent: Callable[[dict[str, Any]], None] | None = None,
    on_submission_started: Callable[[], None] | None = None,
    captcha_audit: dict[str, Any] | None = None,
    attempt_number: int = 1,
    timing: ReservationTiming | None = None,
    run_id: str | None = None,
    order_id: str | None = None,
    captcha_event_context: str | None = None,
) -> Page:
    effective_captcha_audit = captcha_audit if captcha_audit is not None else {}
    if can_submit is not None and not can_submit():
        raise AppointmentWorkflowCancelled("La orden fue pausada antes de resolver el captcha.")
    _validate_reservation_selection(
        page,
        settings,
        expected_details=expected_details,
        expected_person_name=expected_person_name,
        timing=timing,
        timing_prefix="initial_validation",
        captcha_audit=effective_captcha_audit,
    )
    if timing is not None:
        timing.mark("captcha_image_started")
    collect_reservation_captcha_training_samples(
        page,
        settings,
        cancel_event=cancel_event,
        can_submit=can_submit,
        validate_selection=lambda: validate_selected_appointment(
            page,
            expected_details,
            expected_person_name=expected_person_name,
            use_atomic_dom=settings.appointment_atomic_validation_enabled,
        ),
        detection_origin=(expected_details or {}).get("detection_origin"),
        captcha_audit=effective_captcha_audit,
        attempt_number=attempt_number,
        run_id=run_id,
        order_id=order_id,
        event_context=captcha_event_context,
    )
    captcha_path = save_reservation_captcha_image(
        page,
        settings,
        "04-reserva-captcha-tecnico-2captcha",
        captcha_audit=effective_captcha_audit,
    )
    captcha_path_for_solver = captcha_submission_image_path(
        captcha_path,
        effective_captcha_audit,
    )
    if captcha_audit is not None:
        captcha_audit["attempt"] = attempt_number
        captcha_audit["captcha_image_path"] = str(captcha_path_for_solver)
        if captcha_path.exists():
            captcha_audit["captcha_screenshot_image_path"] = str(captcha_path)
        captcha_audit["captcha_sent_source"] = (
            "original_html" if captcha_path_for_solver != captcha_path else "screenshot"
        )
    if timing is not None:
        timing.mark("captcha_image_finished")
    if can_solve_captcha is not None and not can_solve_captcha():
        raise ReservationDeferredForPriority(
            "Reserva diferida porque hay una orden de mayor prioridad lista.",
            dict(captcha_audit or {}),
        )
    shadow_event_id: str | None = None
    shadow_metadata: dict[str, Any] = {}
    if run_id:
        event_namespace = (
            f"{run_id}:{order_id or 'observer'}"
            f"{f':{captcha_event_context}' if captcha_event_context else ''}"
        )
        shadow_event_id = f"{event_namespace}:captcha-{attempt_number}"
        shadow_metadata = {
            "run_id": run_id,
            "order_id": order_id,
            "observer": int(order_id is None),
            "attempt": attempt_number,
            "event_context": captcha_event_context,
            "captured_at_utc": datetime.now(UTC).isoformat(),
            "source_image_kind": effective_captcha_audit.get("captcha_sent_source"),
            "detection_origin": (expected_details or {}).get("detection_origin"),
            "portal_stage": "reservation_captcha",
        }
        if captcha_audit is not None:
            captcha_audit["captcha_shadow_event_id"] = shadow_event_id
    try:
        if timing is not None:
            timing.mark("captcha_solver_started")
        captcha_solver_started = time.monotonic()
        authority_result = solve_reservation_captcha(
            captcha_path_for_solver,
            settings,
            event_id=shadow_event_id,
            run_id=run_id,
            order_id=order_id,
            attempt_number=attempt_number,
            metadata=shadow_metadata,
            fallback_solver=solve_normal_captcha,
        )
        captcha_solution = authority_result.answer
        captcha_solver_duration_ms = round(
            max(time.monotonic() - captcha_solver_started, 0.0) * 1000,
            3,
        )
        shadow_prediction_enqueued = False
        shadow_external_enqueued = False
        if shadow_event_id:
            shadow_prediction_enqueued = enqueue_shadow_prediction(
                event_id=shadow_event_id,
                image_path=str(captcha_path_for_solver.resolve()),
                metadata=shadow_metadata,
            )
            shadow_external_enqueued = enqueue_shadow_external_result(
                event_id=shadow_event_id,
                external_answer=captcha_solution,
                portal_accepted=None,
                external_solve_ms=captcha_solver_duration_ms,
                answer_source=authority_result.source,
            )
        if captcha_audit is not None:
            captcha_audit["captcha_solution_sent"] = captcha_solution
            captcha_audit["captcha_solver_duration_ms"] = captcha_solver_duration_ms
            captcha_audit["captcha_solver_source"] = authority_result.source
            captcha_audit["captcha_authority_decision_id"] = (
                authority_result.decision_id
            )
            captcha_audit["captcha_authority_fallback_reason"] = (
                authority_result.fallback_reason
            )
            captcha_audit["captcha_local_request_ms"] = (
                authority_result.local_request_ms
            )
            captcha_audit["captcha_local_inference_ms"] = (
                authority_result.local_inference_ms
            )
            captcha_audit["captcha_v6_mean_confidence"] = (
                authority_result.mean_confidence
            )
            captcha_audit["captcha_v6_min_char_confidence"] = (
                authority_result.min_char_confidence
            )
            captcha_audit["captcha_v6_sequence_confidence_product"] = (
                authority_result.sequence_confidence_product
            )
            captcha_audit["captcha_local_queue_wait_ms"] = (
                authority_result.local_queue_wait_ms
            )
            captcha_audit["captcha_local_preprocess_ms"] = (
                authority_result.local_preprocess_ms
            )
            captcha_audit["captcha_local_persist_ms"] = (
                authority_result.local_persist_ms
            )
            captcha_audit["captcha_local_service_total_ms"] = (
                authority_result.local_service_total_ms
            )
            captcha_audit["captcha_local_cached"] = authority_result.local_cached
            captcha_audit["captcha_local_coalesced"] = (
                authority_result.local_coalesced
            )
            if shadow_event_id:
                captcha_audit["captcha_shadow_prediction_enqueued"] = (
                    shadow_prediction_enqueued
                )
                captcha_audit["captcha_shadow_external_enqueued"] = (
                    shadow_external_enqueued
                )
        if timing is not None:
            timing.mark("captcha_solver_finished")
    finally:
        logger.info("Preserved captcha image used for submission: %s", captcha_path_for_solver)
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de enviar el captcha de reserva."
        )
    if can_submit is not None and not can_submit():
        raise AppointmentWorkflowCancelled("La orden fue pausada antes de enviar la reserva.")
    _validate_reservation_selection(
        page,
        settings,
        expected_details=expected_details,
        expected_person_name=expected_person_name,
        timing=timing,
        timing_prefix="post_solver_validation",
        captcha_audit=effective_captcha_audit,
    )

    logger.info("Filling reservation captcha field")
    if timing is not None:
        timing.mark("captcha_field_fill_started")
    reservation_field = page.locator(RESERVATION_FIELD_SELECTOR).first
    reservation_field.wait_for(state="visible", timeout=15_000)
    reservation_field.fill(captcha_solution, timeout=15_000)
    if timing is not None:
        timing.mark("captcha_filled")

    logger.info("Clicking reservation button")
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de pulsar el boton de reserva."
        )
    reserve_button = page.locator(RESERVATION_BUTTON_SELECTOR).first
    reserve_button.wait_for(state="visible", timeout=15_000)
    reserve_button.scroll_into_view_if_needed(timeout=15_000)
    final_validation = _validate_reservation_selection(
        page,
        settings,
        expected_details=expected_details,
        expected_person_name=expected_person_name,
        timing=timing,
        timing_prefix="pre_click_validation",
        captcha_audit=effective_captcha_audit,
    )
    if on_submission_intent is not None:
        submission_details = dict(expected_details or {})
        submission_details.update(
            {
                "captcha_field_filled": True,
                "captcha_solver_source": effective_captcha_audit.get(
                    "captcha_solver_source"
                ),
                "captcha_authority_decision_id": effective_captcha_audit.get(
                    "captcha_authority_decision_id"
                ),
                "pre_submit_validation": "passed",
                "pre_submit_validation_mode": final_validation.get("mode"),
                "pre_submit_validation_ms": final_validation.get("duration_ms"),
                "pre_submit_validated_at_utc": datetime.now(UTC).isoformat(),
            }
        )
        if timing is not None:
            timing.mark("submission_intent_started")
        try:
            on_submission_intent(submission_details)
        finally:
            if timing is not None:
                timing.mark("submission_intent_finished")
    try:
        if timing is not None:
            timing.mark("reserve_click_started")
        reserve_button.click(timeout=15_000)
    except PlaywrightError as exc:
        if on_submission_started is not None:
            on_submission_started()
        raise ReservationSubmissionUncertain(
            "El click en Reservar pudo haber sido enviado, pero Playwright no pudo "
            "confirmar la respuesta."
        ) from exc
    if on_submission_started is not None:
        on_submission_started()
    try:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except PlaywrightTimeoutError:
            logger.info("Reservation click did not trigger domcontentloaded before timeout")
        logger.info("Current page after reservation click: %s", page.url)
        if timing is not None:
            timing.mark("portal_response")
    except PlaywrightError as exc:
        raise ReservationSubmissionUncertain(
            "La solicitud de reserva fue enviada, pero la pagina se desconecto antes "
            "de iniciar la verificacion."
        ) from exc
    return page
