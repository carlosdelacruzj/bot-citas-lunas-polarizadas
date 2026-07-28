from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from playwright.sync_api import Page

from appointment_bot.core.models import AvailabilityResult
from appointment_bot.reservation_engine.appointment_reader import (
    read_stable_appointment_snapshot,
    snapshot_details,
)

logger = logging.getLogger(__name__)

IDENTITY_READ_ATTEMPTS = 3
IDENTITY_READ_RETRY_MS = 150
_MASKED_IDENTITY_VALUES = {"", "***", "usuario oculto"}


def _name_tokens(value: str) -> tuple[str, ...]:
    from appointment_bot.utils.sanitization import normalize_option

    return tuple(part for part in normalize_option(value).split() if part)


def _same_person_name(actual: str, expected: str) -> bool:
    actual_tokens = _name_tokens(actual)
    expected_tokens = _name_tokens(expected)
    if not actual_tokens or not expected_tokens:
        return False
    if actual_tokens == expected_tokens:
        return True
    if sorted(actual_tokens) == sorted(expected_tokens):
        return True

    actual_name = " ".join(actual_tokens)
    expected_name = " ".join(expected_tokens)
    return expected_name in actual_name or actual_name in expected_name


def _read_stable_person_name(
    page: Page,
    read_person_name: Callable[[Page], str],
    *,
    expected_person_name: str,
) -> str:
    last_name = ""
    for attempt in range(1, IDENTITY_READ_ATTEMPTS + 1):
        candidate = read_person_name(page).strip()
        normalized_candidate = " ".join(_name_tokens(candidate))
        if normalized_candidate not in _MASKED_IDENTITY_VALUES:
            if _same_person_name(candidate, expected_person_name):
                return candidate
            if candidate == last_name:
                return candidate
            last_name = candidate
        if attempt < IDENTITY_READ_ATTEMPTS:
            page.wait_for_timeout(IDENTITY_READ_RETRY_MS)
    return last_name


def select_available_appointment(
    page: Page,
    *,
    allow_hidden: bool = False,
    include_person: bool = True,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    timeout: int = 15_000,
) -> AvailabilityResult:
    from appointment_bot.reservation_engine.appointments import (
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

    observation_started = time.monotonic()
    observation: dict[str, Any] = {
        "date_postback_seconds": [],
        "hour_stabilization_seconds": [],
    }
    logger.info("Selecting available appointment date and hour")
    options_started = time.monotonic()
    date_options = _real_options(_select_options(page, DATE_SELECTOR))
    observation["date_options_read_seconds"] = round(time.monotonic() - options_started, 3)
    observation["date_candidate_count"] = len(date_options)
    if not date_options:
        raise AppointmentWorkflowUnavailable(
            "Se detecto disponibilidad, pero no se encontro una fecha seleccionable."
        )

    blocked_evidence_candidate: dict[str, str] | None = None
    for date_option in reversed(date_options):
        previous_date = _selected_option_text(page, DATE_SELECTOR)
        previous_hour_signature = _options_signature(_select_options(page, HOUR_SELECTOR))
        date_select = page.locator(DATE_SELECTOR)
        logger.info("Selecting appointment date: %s", date_option["text"])
        postback_started = time.monotonic()
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
        observation["date_postback_seconds"].append(round(time.monotonic() - postback_started, 3))
        real_hour_options = _real_options(hour_options)
        observation["hour_candidate_count"] = observation.get("hour_candidate_count", 0) + len(
            real_hour_options
        )
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
                if blocked_evidence_candidate is None:
                    blocked_evidence_candidate = {
                        "date_text": str(date_option["text"]),
                        "hour_text": str(hour_option["text"]),
                    }
                continue

            hour_select = page.locator(HOUR_SELECTOR)
            logger.info("Selecting appointment hour: %s", hour_option["text"])
            _select_appointment_option(
                hour_select,
                hour_option["value"],
                allow_hidden=allow_hidden,
            )
            stabilization_started = time.monotonic()
            page.wait_for_timeout(500)

            snapshot = read_stable_appointment_snapshot(page, log_person=include_person)
            observation["hour_stabilization_seconds"].append(
                round(time.monotonic() - stabilization_started, 3)
            )
            if _same_option(snapshot.date, date_option["text"]) and _same_option(
                snapshot.hour, hour_option["text"]
            ):
                return _with_selection_observation(
                    AvailabilityResult(
                        status="available",
                        message="Se seleccionaron una fecha y una hora disponibles.",
                        details=snapshot_details(snapshot, include_person=include_person),
                    ),
                    observation,
                    observation_started,
                )

            logger.warning(
                "Appointment selection was not preserved for date %s and hour %s",
                date_option["text"],
                hour_option["text"],
            )

    if blocked_evidence_candidate is not None:
        blocked_evidence_result = _select_blocked_appointment_for_evidence(
            page,
            blocked_evidence_candidate,
            allow_hidden=allow_hidden,
            include_person=include_person,
            timeout=timeout,
            observation=observation,
        )
        return _with_selection_observation(
            blocked_evidence_result, observation, observation_started
        )

    snapshot = read_stable_appointment_snapshot(page, log_person=include_person)
    details = snapshot_details(snapshot, include_person=include_person)
    if is_allowed_appointment is not None:
        details["blocked_by_order_rule"] = True
    return _with_selection_observation(
        AvailabilityResult(
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
        ),
        observation,
        observation_started,
    )


def _select_blocked_appointment_for_evidence(
    page: Page,
    candidate: dict[str, str],
    *,
    allow_hidden: bool,
    include_person: bool,
    timeout: int,
    observation: dict[str, Any],
) -> AvailabilityResult:
    from appointment_bot.reservation_engine.appointments import (
        DATE_SELECTOR,
        HOUR_SELECTOR,
        _options_signature,
        _real_options,
        _same_option,
        _select_appointment_option,
        _select_options,
        _selected_option_text,
        _wait_for_options_after_selection,
    )

    date_text = candidate["date_text"]
    hour_text = candidate["hour_text"]
    message = (
        "Se encontro un horario disponible, pero no cumple "
        "la regla de reserva de la orden."
    )
    try:
        matching_date = next(
            (
                option
                for option in _real_options(_select_options(page, DATE_SELECTOR))
                if _same_option(str(option["text"]), date_text)
            ),
            None,
        )
        if matching_date is None:
            return _blocked_evidence_unavailable_result(
                page,
                message=message,
                date_text=date_text,
                hour_text=hour_text,
                reason="La fecha bloqueada dejo de estar disponible al preparar la evidencia.",
                include_person=include_person,
            )
        previous_date = _selected_option_text(page, DATE_SELECTOR)
        previous_hour_signature = _options_signature(_select_options(page, HOUR_SELECTOR))
        logger.info(
            "Reselecting blocked appointment for evidence: %s %s",
            date_text,
            hour_text,
        )
        postback_started = time.monotonic()
        _select_appointment_option(
            page.locator(DATE_SELECTOR),
            str(matching_date["value"]),
            allow_hidden=allow_hidden,
        )
        hour_options = _wait_for_options_after_selection(
            page,
            HOUR_SELECTOR,
            previous_signature=previous_hour_signature,
            require_change=not _same_option(previous_date, date_text),
            timeout=timeout,
        )
        observation["date_postback_seconds"].append(
            round(time.monotonic() - postback_started, 3)
        )
        matching_hour = next(
            (
                option
                for option in _real_options(hour_options)
                if _same_option(str(option["text"]), hour_text)
            ),
            None,
        )
        if matching_hour is None:
            return _blocked_evidence_unavailable_result(
                page,
                message=message,
                date_text=date_text,
                hour_text=hour_text,
                reason="El horario bloqueado dejo de estar disponible al preparar la evidencia.",
                include_person=include_person,
            )

        _select_appointment_option(
            page.locator(HOUR_SELECTOR),
            str(matching_hour["value"]),
            allow_hidden=allow_hidden,
        )
        stabilization_started = time.monotonic()
        page.wait_for_timeout(500)
        snapshot = read_stable_appointment_snapshot(page, log_person=include_person)
        observation["hour_stabilization_seconds"].append(
            round(time.monotonic() - stabilization_started, 3)
        )
        if not (
            _same_option(snapshot.date, date_text)
            and _same_option(snapshot.hour, hour_text)
        ):
            return _blocked_evidence_unavailable_result(
                page,
                message=message,
                date_text=date_text,
                hour_text=hour_text,
                reason=(
                    "La seleccion bloqueada cambio al preparar la evidencia; "
                    "se conserva el resultado sin iniciar una reserva."
                ),
                include_person=include_person,
            )

        details = snapshot_details(snapshot, include_person=include_person)
        details["blocked_by_order_rule"] = True
        details["blocked_selected_for_evidence"] = True
        details["blocked_evidence_synchronized"] = True
        return AvailabilityResult(status="partial", message=message, details=details)
    except Exception as exc:
        logger.warning(
            "Could not synchronize blocked appointment evidence; "
            "preserving blocked result without reservation: %s",
            exc,
        )
        return _blocked_evidence_unavailable_result(
            page,
            message=message,
            date_text=date_text,
            hour_text=hour_text,
            reason=str(exc),
            include_person=include_person,
        )


def _blocked_evidence_unavailable_result(
    page: Page,
    *,
    message: str,
    date_text: str,
    hour_text: str,
    reason: str,
    include_person: bool,
) -> AvailabilityResult:
    details: dict[str, Any] = {
        "blocked_by_order_rule": True,
        "blocked_evidence_synchronized": False,
        "blocked_evidence_date": date_text,
        "blocked_evidence_hour": hour_text,
        "blocked_evidence_error": reason,
    }
    try:
        snapshot = read_stable_appointment_snapshot(page, log_person=include_person)
    except Exception as exc:
        logger.warning("Could not read fallback blocked appointment snapshot: %s", exc)
    else:
        details.update(snapshot_details(snapshot, include_person=include_person))
    return AvailabilityResult(status="partial", message=message, details=details)


def _with_selection_observation(
    result: AvailabilityResult,
    observation: dict[str, Any],
    started: float,
) -> AvailabilityResult:
    details = dict(result.details or {})
    details["selection_observation"] = {
        **observation,
        "total_seconds": round(time.monotonic() - started, 3),
    }
    return replace(result, details=details)


def has_available_date_options(page: Page) -> bool:
    from appointment_bot.reservation_engine.appointments import (
        DATE_SELECTOR,
        _real_options,
        _select_options,
    )

    return bool(_real_options(_select_options(page, DATE_SELECTOR)))


def validate_selected_appointment(
    page: Page,
    expected_details: dict[str, Any] | None,
    *,
    expected_person_name: str | None = None,
) -> None:
    from appointment_bot.reservation_engine.appointments import (
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
    if expected_person_name:
        actual_person_name = _read_stable_person_name(
            page,
            _read_person_name,
            expected_person_name=expected_person_name,
        )
        if not actual_person_name:
            logger.warning(
                "Could not read a stable portal identity before reservation submission"
            )
            raise AppointmentWorkflowUnavailable(
                "No se pudo validar de forma estable la identidad mostrada por el portal."
            )
        if not _same_person_name(actual_person_name, expected_person_name):
            logger.warning(
                "Portal identity mismatch after stable reread: expected_tokens=%s actual_tokens=%s",
                len(_name_tokens(expected_person_name)),
                len(_name_tokens(actual_person_name)),
            )
            raise AppointmentWorkflowUnavailable(
                "La identidad mostrada por el portal no coincide con la persona de la orden."
            )
