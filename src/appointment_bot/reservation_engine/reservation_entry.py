from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from playwright.sync_api import Error as PlaywrightError

from appointment_bot.reservation_engine.appointment_contracts import (
    AppointmentWorkflowCancelled,
    PortalContractChanged,
    ReservationSubmissionUncertain,
)
from appointment_bot.reservation_engine.appointment_selection import validate_selected_appointment
from appointment_bot.reservation_engine.reservation_controls import RESERVATION_BUTTON_SELECTOR
from appointment_bot.reservation_engine.reservation_post_audit import (
    ReservationPostCollector,
    inspect_reservation_form,
    validate_reservation_form_audit,
)
from appointment_bot.utils.diagnostics import save_sanitized_page_html
from appointment_bot.utils.screenshots import save_screenshot

logger = logging.getLogger(__name__)


def click_preverified_reservation(
    page, settings, *, expected_details, expected_person_name, cancel_event,
    can_submit, on_submission_intent, on_submission_started, audit, timing,
) -> None:
    """Send the known pre-access-only form once, under the durable submit guards."""
    if not settings.auto_reserve:
        raise AppointmentWorkflowCancelled("La reserva automatica esta desactivada.")
    if not (expected_details or {}).get("canonical_slot_capture"):
        raise PortalContractChanged("Falta la captura canonica antes del boton de reserva.")

    def ensure_owned():
        if (cancel_event is not None and cancel_event.is_set()) or (
            can_submit is not None and not can_submit()
        ):
            raise AppointmentWorkflowCancelled("La orden perdio permiso antes del clic de reserva.")

    ensure_owned()
    validate_selected_appointment(page, expected_details, expected_person_name=expected_person_name)
    baseline = inspect_reservation_form(page)
    validate_reservation_form_audit(
        baseline, require_captcha_answer=False, require_math_question=False, pre_access_only=True,
    )
    audit["captcha_kind"] = "pre_access_verified"
    audit["reservation_button_interaction"] = {
        "started_at": datetime.now(UTC).isoformat(),
        "mode": "pre_access_only_submit",
        "clicked": False,
    }
    interaction = audit["reservation_button_interaction"]
    audit["pre_submit_form_audits"] = [baseline]
    button = page.locator(RESERVATION_BUTTON_SELECTOR)
    button.wait_for(state="visible", timeout=5000)
    button.scroll_into_view_if_needed(timeout=5000)
    if not button.is_enabled():
        raise PortalContractChanged("El boton de reserva sigue deshabilitado.")
    if on_submission_intent is not None:
        on_submission_intent({**expected_details, "pre_submit_validation": "passed",
                              "reservation_button_interaction": dict(interaction)})
    ensure_owned()
    validate_selected_appointment(page, expected_details, expected_person_name=expected_person_name)
    final_audit = inspect_reservation_form(page)
    validate_reservation_form_audit(
        final_audit, require_captcha_answer=False,
        require_math_question=False, pre_access_only=True,
    )
    if baseline["form_contract_sha256"] != final_audit["form_contract_sha256"]:
        raise PortalContractChanged("El formulario cambio antes del clic de reserva.")
    post_audit = {"request_seen": False}
    audit["reservation_post_audit"] = post_audit
    audit["entry_post_audit"] = post_audit
    collector = ReservationPostCollector(post_audit)
    started = time.monotonic()
    collector.attach(page)
    try:
        ensure_owned()
        # Persist pending before the possible send; a failed click remains ambiguous.
        if on_submission_started is not None:
            on_submission_started()
        interaction["clicked"] = True
        if timing is not None:
            timing.mark("reserve_click_started")
        button.click(timeout=15000)
        collector.wait_for_response(page)
        if timing is not None:
            timing.mark("portal_response")
        logger.info("Preverified reservation click: HTTP=%s", post_audit.get("response_status"))
    except PlaywrightError as exc:
        raise ReservationSubmissionUncertain(
            "El boton Reservar Cita pudo enviar la solicitud; no se repetira el clic."
        ) from exc
    finally:
        collector.detach(page)
        interaction["duration_seconds"] = round(time.monotonic() - started, 3)
        for key, save, label in (
            ("entry_screenshot_path", save_screenshot, "reserva-respuesta-primer-boton"),
            ("entry_html_path", save_sanitized_page_html, "reserva-respuesta-primer-boton"),
        ):
            try:
                path = save(page, settings, label)
                if path is not None:
                    audit[key] = str(path)
            except Exception:
                logger.exception("Could not preserve reservation entry artifact: %s", key)
