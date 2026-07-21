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
from appointment_bot.reservation_engine.reservation_controls import (
    RESERVATION_BUTTON_SELECTOR,
    RESERVATION_FIELD_SELECTOR,
)
from appointment_bot.reservation_engine.timings import ReservationTiming
from appointment_bot.services.captcha import solve_normal_captcha
from appointment_bot.services.captcha_shadow import (
    enqueue_shadow_external_result,
    enqueue_shadow_prediction,
)
from appointment_bot.utils.screenshots import save_screenshot

logger = logging.getLogger(__name__)


def solve_reservation_captcha_and_click_reserve(
    page: Page,
    settings: Settings,
    *,
    cancel_event: threading.Event | None = None,
    can_submit: Callable[[], bool] | None = None,
    can_solve_captcha: Callable[[], bool] | None = None,
    expected_details: dict[str, Any] | None = None,
    expected_person_name: str | None = None,
    on_submission_intent: Callable[[], None] | None = None,
    on_submission_started: Callable[[], None] | None = None,
    captcha_audit: dict[str, Any] | None = None,
    attempt_number: int = 1,
    timing: ReservationTiming | None = None,
    run_id: str | None = None,
    order_id: str | None = None,
) -> Page:
    if can_submit is not None and not can_submit():
        raise AppointmentWorkflowCancelled("La orden fue pausada antes de resolver el captcha.")
    validate_selected_appointment(page, expected_details, expected_person_name=expected_person_name)
    if timing is not None:
        timing.mark("captcha_image_started")
    effective_captcha_audit = captcha_audit if captcha_audit is not None else {}
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
    if run_id:
        shadow_event_id = (
            f"{run_id}:{order_id or 'observer'}:captcha-{attempt_number}"
        )
        shadow_metadata = {
            "run_id": run_id,
            "order_id": order_id,
            "observer": int(order_id is None),
            "attempt": attempt_number,
            "captured_at_utc": datetime.now(UTC).isoformat(),
            "source_image_kind": effective_captcha_audit.get("captcha_sent_source"),
            "detection_origin": (expected_details or {}).get("detection_origin"),
            "portal_stage": "reservation_captcha",
        }
        shadow_enqueued = enqueue_shadow_prediction(
            event_id=shadow_event_id,
            image_path=str(captcha_path_for_solver.resolve()),
            metadata=shadow_metadata,
        )
        if captcha_audit is not None:
            captcha_audit["captcha_shadow_event_id"] = shadow_event_id
            captcha_audit["captcha_shadow_prediction_enqueued"] = shadow_enqueued
    try:
        if timing is not None:
            timing.mark("captcha_solver_started")
        captcha_solver_started = time.monotonic()
        captcha_solution = solve_normal_captcha(captcha_path_for_solver, settings)
        captcha_solver_duration_ms = round(
            max(time.monotonic() - captcha_solver_started, 0.0) * 1000,
            3,
        )
        if captcha_audit is not None:
            captcha_audit["captcha_solution_sent"] = captcha_solution
            captcha_audit["captcha_solver_duration_ms"] = captcha_solver_duration_ms
            shadow_event_id = captcha_audit.get("captcha_shadow_event_id")
            if shadow_event_id:
                captcha_audit["captcha_shadow_external_enqueued"] = (
                    enqueue_shadow_external_result(
                        event_id=str(shadow_event_id),
                        external_answer=captcha_solution,
                        portal_accepted=None,
                        external_solve_ms=captcha_solver_duration_ms,
                    )
                )
        if timing is not None:
            timing.mark("captcha_solver_finished")
    finally:
        logger.info("Preserved captcha image sent to 2captcha: %s", captcha_path_for_solver)
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de enviar el captcha de reserva."
        )
    if can_submit is not None and not can_submit():
        raise AppointmentWorkflowCancelled("La orden fue pausada antes de enviar la reserva.")
    validate_selected_appointment(page, expected_details, expected_person_name=expected_person_name)

    logger.info("Filling reservation captcha field")
    reservation_field = page.locator(RESERVATION_FIELD_SELECTOR).first
    reservation_field.wait_for(state="visible", timeout=15_000)
    reservation_field.fill(captcha_solution, timeout=15_000)
    if timing is not None:
        timing.mark("captcha_filled")
    if captcha_audit is not None:
        pre_submit_path = save_screenshot(
            page,
            settings,
            f"05-reserva-antes-de-enviar-intento-{attempt_number}",
        )
        if pre_submit_path is not None:
            captcha_audit["pre_submit_screenshot_path"] = str(pre_submit_path)

    logger.info("Clicking reservation button")
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de pulsar el boton de reserva."
        )
    reserve_button = page.locator(RESERVATION_BUTTON_SELECTOR).first
    reserve_button.wait_for(state="visible", timeout=15_000)
    reserve_button.scroll_into_view_if_needed(timeout=15_000)
    validate_selected_appointment(page, expected_details, expected_person_name=expected_person_name)
    if on_submission_intent is not None:
        on_submission_intent()
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
