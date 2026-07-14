from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from playwright.sync_api import Page

from appointment_bot.domain import AvailabilityResult
from appointment_bot.reservation_engine.appointment_fetch_probe import (
    read_fetch_probe_appointment_snapshot,
)

logger = logging.getLogger(__name__)
LIMA_TZ = ZoneInfo("America/Lima")


def read_appointment_availability(
    page: Page,
    *,
    include_person: bool = True,
    timeout: int = 30_000,
) -> AvailabilityResult:
    logger.debug("Checking appointment availability")
    page.wait_for_load_state("domcontentloaded", timeout=timeout)

    snapshot = read_stable_appointment_snapshot(page, log_person=include_person)
    result = availability_result_from_snapshot(
        page,
        snapshot,
        include_person=include_person,
    )
    if result.status == "partial":
        logger.info("Partial availability detected; rechecking before notifying")
        page.wait_for_timeout(1_500)
        snapshot = read_stable_appointment_snapshot(page, log_person=include_person)
        result = availability_result_from_snapshot(
            page,
            snapshot,
            include_person=include_person,
        )

    result = apply_fetch_probe_if_needed(page, result, include_person=include_person)

    details = snapshot_details(snapshot, include_person=False)
    details.update(_read_site_refresh_evidence(page))
    if details:
        result_details = dict(result.details or {})
        result_details.update(
            {
                key: value
                for key, value in details.items()
                if key.startswith("site_refresh_")
            }
        )
        result = AvailabilityResult(result.status, result.message, result_details)
    logger.info(
        "Appointment summary: site=%s date=%s hour=%s",
        (result.details or details).get("sede", "unknown"),
        (result.details or details).get("fecha", "unknown"),
        (result.details or details).get("hora", "unknown"),
    )
    return result


def apply_fetch_probe_if_needed(
    page: Page,
    result: AvailabilityResult,
    *,
    include_person: bool,
) -> AvailabilityResult:
    if result.status == "available":
        return result

    fetch_snapshot = read_fetch_probe_appointment_snapshot(page)
    if fetch_snapshot is None:
        return result

    fetch_result = availability_result_from_snapshot(
        page,
        fetch_snapshot,
        include_person=include_person,
    )
    if fetch_result.status not in {"available", "partial"}:
        return result

    details = dict(fetch_result.details or {})
    details["fetch_probe"] = True
    details["modal_must_remain_open"] = True
    return AvailabilityResult(
        status=fetch_result.status,
        message=(
            f"{fetch_result.message} "
            "La disponibilidad fue detectada por consulta directa al formulario."
        ),
        details=details,
    )


def availability_result_from_snapshot(
    page: Page,
    snapshot,
    *,
    include_person: bool = True,
) -> AvailabilityResult:
    from appointment_bot.reservation_engine.appointments import AVAILABLE_TEXTS, UNAVAILABLE_TEXTS

    date_options = snapshot.date_options
    hour_options = snapshot.hour_options
    details = snapshot_details(snapshot, include_person=include_person)
    has_date_options = _has_real_options(date_options)
    has_hour_options = _has_real_options(hour_options)

    if has_date_options and has_hour_options:
        return AvailabilityResult(
            status="available",
            message="Se detectaron opciones seleccionables de fecha y hora.",
            details=details,
        )

    if has_date_options and not has_hour_options:
        if _only_non_actionable_dates(date_options):
            details["blocked_by_current_day"] = True
            return AvailabilityResult(
                status="unavailable",
                message=(
                    "El portal solo muestra fechas del dia actual o anteriores "
                    "sin una hora seleccionable."
                ),
                details=details,
            )
        return AvailabilityResult(
            status="partial",
            message="Se detecto fecha disponible, pero aun no hay hora seleccionable.",
            details=details,
        )

    if has_hour_options and not has_date_options:
        return AvailabilityResult(
            status="partial",
            message="Se detecto hora disponible, pero no se detecto fecha seleccionable.",
            details=details,
        )

    if _only_no_slots(date_options) and _only_no_slots(hour_options):
        return AvailabilityResult(
            status="unavailable",
            message="La pagina muestra 'Sin Cupos' en fecha y hora.",
            details=details,
        )

    content = page.locator("body").inner_text(timeout=15_000).lower()

    if any(text in content for text in AVAILABLE_TEXTS):
        return AvailabilityResult(
            status="partial",
            message=(
                "Se detecto texto compatible con cupo disponible, "
                "pero no hay fecha y hora seleccionables."
            ),
            details=details,
        )

    if any(text in content for text in UNAVAILABLE_TEXTS):
        return AvailabilityResult(
            status="unavailable",
            message="Se detecto texto compatible con falta de cupos.",
            details=details,
        )

    return AvailabilityResult(
        status="unknown",
        message=(
            "No se pudo determinar la disponibilidad con los textos actuales. "
            "Ajusta AVAILABLE_TEXTS o UNAVAILABLE_TEXTS en flows/appointments.py."
        ),
        details=details,
    )


def read_stable_appointment_snapshot(
    page: Page,
    *,
    log_person: bool,
) -> object:
    previous_snapshot = None
    current_snapshot = None
    for attempt in range(1, 5):
        current_snapshot = read_appointment_snapshot(page)
        logger.debug(
            "Appointment snapshot %s: %s",
            attempt,
            snapshot_details(current_snapshot, include_person=False),
        )
        logger.debug("Date options: %s", current_snapshot.date_options)
        logger.debug("Hour options: %s", current_snapshot.hour_options)

        if (
            previous_snapshot is not None
            and current_snapshot.signature() == previous_snapshot.signature()
        ):
            return current_snapshot

        previous_snapshot = current_snapshot
        page.wait_for_timeout(750)

    if current_snapshot is None:
        raise RuntimeError("Could not read appointment availability controls.")
    return current_snapshot


def read_appointment_snapshot(page: Page):
    from appointment_bot.reservation_engine.appointments import (
        DATE_SELECTOR,
        HOUR_SELECTOR,
        SITE_SELECTOR,
        AppointmentSnapshot,
        _read_person_name,
        _read_slots_value,
        _select_options_text,
        _selected_option_text,
    )

    site_options = _select_options_text(page, SITE_SELECTOR)
    date_options = _select_options_text(page, DATE_SELECTOR)
    hour_options = _select_options_text(page, HOUR_SELECTOR)
    return AppointmentSnapshot(
        site_options=site_options,
        date_options=date_options,
        hour_options=hour_options,
        site=_selected_option_text(page, SITE_SELECTOR),
        date=_selected_option_text(page, DATE_SELECTOR),
        hour=_selected_option_text(page, HOUR_SELECTOR),
        slots=_read_slots_value(page),
        person_name=_read_person_name(page),
    )


def snapshot_details(
    snapshot,
    *,
    include_person: bool = True,
) -> dict[str, Any]:
    details = {
        "sede": _real_or_selected(snapshot.site, snapshot.site_options),
        "fecha": _real_or_selected(snapshot.date, snapshot.date_options),
        "hora": _real_or_selected(snapshot.hour, snapshot.hour_options),
        "cupos": snapshot.slots,
        "date_options": snapshot.date_options,
        "hour_options": snapshot.hour_options,
    }
    if include_person:
        details["nombre"] = snapshot.person_name
    return {key: value for key, value in details.items() if value}


def _real_or_selected(selected: str, options: list[str]) -> str:
    if selected and _has_real_options([selected]):
        return selected
    return next((option for option in options if _has_real_options([option])), selected)


def _read_site_refresh_evidence(page: Page) -> dict[str, Any]:
    from playwright.sync_api import Error as PlaywrightError

    try:
        data = page.evaluate("() => window.__appointmentBotLastSiteRefresh || null")
    except PlaywrightError:
        return {}
    return dict(data or {})


def _only_no_slots(options: list[str]) -> bool:
    return bool(options) and all(option.lower() == "sin cupos" for option in options)


def _has_real_options(options: list[str]) -> bool:
    return any(_is_real_appointment_option(option) for option in options)


def _is_real_appointment_option(option: dict[str, Any] | str) -> bool:
    if isinstance(option, str):
        text = option
        value_present = True
        disabled = False
        hidden = False
    else:
        text = str(option.get("text") or "")
        value_present = bool(option.get("value"))
        disabled = bool(option.get("disabled"))
        hidden = bool(option.get("hidden"))
    normalized = text.strip().lower()
    return (
        value_present
        and not disabled
        and not hidden
        and bool(normalized)
        and normalized != "sin cupos"
        and not normalized.startswith("seleccione")
    )


def _only_non_actionable_dates(options: list[str]) -> bool:
    real_options = [option for option in options if _is_real_appointment_option(option)]
    if not real_options:
        return False
    today = datetime.now(LIMA_TZ).date()
    parsed_dates = []
    for option in real_options:
        try:
            parsed_dates.append(datetime.strptime(option.strip(), "%d/%m/%Y").date())
        except ValueError:
            return False
    return all(value <= today for value in parsed_dates)
