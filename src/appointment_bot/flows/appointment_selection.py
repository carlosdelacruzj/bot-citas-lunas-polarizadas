from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page

from appointment_bot.domain import AvailabilityResult
from appointment_bot.flows.appointment_reader import (
    read_stable_appointment_snapshot,
    snapshot_details,
)

logger = logging.getLogger(__name__)


def select_available_appointment(
    page: Page,
    *,
    allow_hidden: bool = False,
    include_person: bool = True,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    timeout: int = 15_000,
) -> AvailabilityResult:
    from appointment_bot.flows.appointments import (
        DATE_SELECTOR,
        HOUR_SELECTOR,
        AppointmentWorkflowUnavailable,
        _options_signature,
        _real_options,
        _same_option,
        _select_appointment_option,
        _select_options,
        _selected_option_text,
        _wait_for_options_after_selection,
    )

    logger.info("Selecting available appointment date and hour")
    date_options = _real_options(_select_options(page, DATE_SELECTOR))
    if not date_options:
        raise AppointmentWorkflowUnavailable(
            "Se detecto disponibilidad, pero no se encontro una fecha seleccionable."
        )

    blocked_evidence_result: AvailabilityResult | None = None
    for date_option in reversed(date_options):
        previous_date = _selected_option_text(page, DATE_SELECTOR)
        previous_hour_signature = _options_signature(_select_options(page, HOUR_SELECTOR))
        date_select = page.locator(DATE_SELECTOR)
        logger.info("Selecting appointment date: %s", date_option["text"])
        _select_appointment_option(
            date_select,
            date_option["value"],
            allow_hidden=allow_hidden,
        )
        hour_options = _wait_for_options_after_selection(
            page,
            HOUR_SELECTOR,
            previous_signature=previous_hour_signature,
            require_change=not _same_option(previous_date, date_option["text"]),
            timeout=timeout,
        )
        real_hour_options = _real_options(hour_options)
        if not real_hour_options:
            logger.info("No selectable hours found for date %s", date_option["text"])
            continue

        for hour_option in reversed(real_hour_options):
            if is_allowed_appointment is not None and not is_allowed_appointment(
                str(date_option["text"]),
                str(hour_option["text"]),
            ):
                logger.info(
                    "Skipping appointment by order rule: %s %s",
                    date_option["text"],
                    hour_option["text"],
                )
                if blocked_evidence_result is None:
                    hour_select = page.locator(HOUR_SELECTOR)
                    _select_appointment_option(
                        hour_select,
                        hour_option["value"],
                        allow_hidden=allow_hidden,
                    )
                    page.wait_for_timeout(500)
                    snapshot = read_stable_appointment_snapshot(
                        page,
                        log_person=include_person,
                    )
                    details = snapshot_details(snapshot, include_person=include_person)
                    details["blocked_by_order_rule"] = True
                    details["blocked_selected_for_evidence"] = True
                    blocked_evidence_result = AvailabilityResult(
                        status="partial",
                        message=(
                            "Se encontro un horario disponible, pero no cumple "
                            "la regla de reserva de la orden."
                        ),
                        details=details,
                    )
                continue

            hour_select = page.locator(HOUR_SELECTOR)
            logger.info("Selecting appointment hour: %s", hour_option["text"])
            _select_appointment_option(
                hour_select,
                hour_option["value"],
                allow_hidden=allow_hidden,
            )
            page.wait_for_timeout(500)

            snapshot = read_stable_appointment_snapshot(page, log_person=include_person)
            if _same_option(snapshot.date, date_option["text"]) and _same_option(
                snapshot.hour, hour_option["text"]
            ):
                return AvailabilityResult(
                    status="available",
                    message="Se seleccionaron una fecha y una hora disponibles.",
                    details=snapshot_details(snapshot, include_person=include_person),
                )

            logger.warning(
                "Appointment selection was not preserved for date %s and hour %s",
                date_option["text"],
                hour_option["text"],
            )

    if blocked_evidence_result is not None:
        return blocked_evidence_result

    snapshot = read_stable_appointment_snapshot(page, log_person=include_person)
    details = snapshot_details(snapshot, include_person=include_person)
    if is_allowed_appointment is not None:
        details["blocked_by_order_rule"] = True
    return AvailabilityResult(
        status="partial",
        message=(
            "Se encontraron fechas y horas disponibles, pero ninguna cumple "
            "la regla de reserva de la orden."
            if is_allowed_appointment is not None
            else (
                "Se encontraron fechas disponibles, pero ninguna tiene una hora "
                "seleccionable y estable por ahora."
            )
        ),
        details=details,
    )


def has_available_date_options(page: Page) -> bool:
    from appointment_bot.flows.appointments import DATE_SELECTOR, _real_options, _select_options

    return bool(_real_options(_select_options(page, DATE_SELECTOR)))


def validate_selected_appointment(
    page: Page,
    expected_details: dict[str, Any] | None,
    *,
    expected_person_name: str | None = None,
) -> None:
    from appointment_bot.flows.appointments import (
        DATE_SELECTOR,
        HOUR_SELECTOR,
        SITE_SELECTOR,
        AppointmentWorkflowUnavailable,
        _read_person_name,
        _read_slots_value,
        _same_option,
        _selected_option_text,
    )
    from appointment_bot.utils.sanitization import normalize_option

    expected_details = expected_details or {}
    expected_site = str(expected_details.get("sede") or "")
    expected_date = str(expected_details.get("fecha") or "")
    expected_hour = str(expected_details.get("hora") or "")
    actual_site = _selected_option_text(page, SITE_SELECTOR)
    actual_date = _selected_option_text(page, DATE_SELECTOR)
    actual_hour = _selected_option_text(page, HOUR_SELECTOR)
    actual_slots = _read_slots_value(page)
    if (
        (expected_site and not _same_option(actual_site, expected_site))
        or (expected_date and not _same_option(actual_date, expected_date))
        or (expected_hour and not _same_option(actual_hour, expected_hour))
    ):
        raise AppointmentWorkflowUnavailable(
            "La sede, fecha u hora seleccionadas cambiaron antes de enviar la reserva."
        )
    if not actual_site or not actual_date or not actual_hour:
        raise AppointmentWorkflowUnavailable(
            "La sede, fecha y hora deben seguir seleccionadas antes de enviar la reserva."
        )
    normalized_slots = normalize_option(actual_slots)
    if normalized_slots in {"0", "sin cupos", "sin cupos disponibles"}:
        raise AppointmentWorkflowUnavailable(
            "El portal indica que el cupo seleccionado ya no esta disponible."
        )
    actual_person_name = _read_person_name(page)
    if expected_person_name and actual_person_name:
        expected_name = normalize_option(expected_person_name)
        actual_name = normalize_option(actual_person_name)
        if expected_name not in actual_name and actual_name not in expected_name:
            raise AppointmentWorkflowUnavailable(
                "La identidad mostrada por el portal no coincide con la persona de la orden."
            )
