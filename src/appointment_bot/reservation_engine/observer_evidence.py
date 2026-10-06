from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from unicodedata import combining, normalize
from zoneinfo import ZoneInfo

from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.core.appointment_budget import evidence_appointment_review
from appointment_bot.core.models import AvailabilityResult
from appointment_bot.core.rules import parse_appointment_date
from appointment_bot.reservation_engine.appointment_contracts import DATE_SELECTOR, HOUR_SELECTOR
from appointment_bot.reservation_engine.appointment_dom import (
    real_options,
    select_appointment_option,
    select_options,
    selected_option_text,
)
from appointment_bot.reservation_engine.appointment_selection import select_available_appointment
from appointment_bot.reservation_engine.appointments import (
    _mark_aspnet_async_refresh,
    _mark_select_for_refresh,
)
from appointment_bot.reservation_engine.slot_evidence import capture_canonical_selected_slot
from appointment_bot.utils.sanitization import normalize_option


def _ensure_live_collection(page) -> None:
    text = normalize_option(page.locator("body").inner_text())
    text = "".join(character for character in normalize("NFKD", text)
                   if not combining(character))
    for signal in (
        "demasiadas consultas", "demasiadas solicitudes", "no disponible temporalmente",
        "sesion expiro", "sesion expirada", "session expired", "inicie sesion",
    ):
        if signal in text:
            reason = "demasiadas solicitudes" if signal == "demasiadas consultas" else signal
            raise RuntimeError(f"Recorrido de evidencia detenido: {reason}.")


def _select_collection_date(page, target: str, timeout: int) -> None:
    if selected_option_text(page, DATE_SELECTOR) == target:
        return
    option = next(item for item in real_options(select_options(page, DATE_SELECTOR))
                  if str(item["text"]) == target)
    marker = _mark_select_for_refresh(page, DATE_SELECTOR)
    async_token = _mark_aspnet_async_refresh(page)
    select_appointment_option(page.locator(DATE_SELECTOR), option["value"], allow_hidden=True)
    # Equal hour lists across dates still require a confirmed postback, not a changed list.
    page.wait_for_function(
        """expected => {
            const date = document.querySelector(expected.selector);
            const manager = window.Sys?.WebForms?.PageRequestManager?.getInstance();
            const refreshed = date?.dataset.appointmentBotRefresh !== expected.marker
                || (expected.asyncToken
                    && window.__appointmentBotAsyncRefreshes?.[expected.asyncToken]);
            return date && refreshed && !manager?.get_isInAsyncPostBack()
                && date.selectedOptions[0]?.textContent.trim() === expected.date;
        }""",
        arg={"selector": DATE_SELECTOR, "marker": marker,
             "asyncToken": async_token, "date": target},
        timeout=timeout,
    )


def collect_observer_evidence(
    page, initial: AvailabilityResult, *, progress: dict,
    should_continue: Callable[[], bool], evidence_settings: EvidenceSettings, timeout: int,
    on_verified_slot: Callable[[AvailabilityResult, Path], None] | None = None,
) -> None:
    """Supplement a completed one-slot detection with at most two read-only reviews."""
    day = datetime.now(ZoneInfo("America/Lima")).date().isoformat()
    progress.update(day=day, initial_status=initial.status, session_queries=1, session_captures=[])
    captured = progress.setdefault("captured", [])
    visits = progress.get("visits") or {}
    progress["visits"] = visits
    completed = progress.setdefault("completed_dates", [])

    def update_completed(date: str) -> None:
        hours = [str(option["text"])
                 for option in real_options(select_options(page, HOUR_SELECTOR))]
        if hours and all([date, hour] in captured for hour in hours) and date not in completed:
            completed.append(date)
        elif any([date, hour] not in captured for hour in hours) and date in completed:
            completed.remove(date)

    def capture(result: AvailabilityResult, *, notify: bool = True) -> None:
        _ensure_live_collection(page)
        result, _, archived = capture_canonical_selected_slot(
            page, result, evidence_settings=evidence_settings, phase="observer_evidence",
        )
        details = result.details or {}
        pair = [str(details["fecha"]), str(details["hora"])]
        if pair not in captured:
            captured.append(pair)
        progress["session_captures"].append({
            "site": details.get("sede"), "date": pair[0], "hour": pair[1],
            "slots": details["cupos"], "path": str(archived),
            "verified_at": datetime.now(ZoneInfo("America/Lima")).isoformat(),
        })
        if notify and on_verified_slot is not None:
            on_verified_slot(result, archived)

    if not should_continue():
        return
    if initial.status == "available":
        capture(initial, notify=False)
        initial_date = str((initial.details or {}).get("fecha") or "")
        visits[initial_date] = visits.get(initial_date, 0) + 1
        update_completed(initial_date)
    for _ in range(2):
        if (not should_continue()
                or datetime.now(ZoneInfo("America/Lima")).date().isoformat() != day):
            return
        _ensure_live_collection(page)
        dates = [str(option["text"]) for option in real_options(select_options(page, DATE_SELECTOR))
                 if parse_appointment_date(str(option["text"])) is not None]
        progress["listed_dates"] = dates
        dates = [date for date in dates if date not in completed]
        if not dates:
            return
        target = min(dates, key=lambda value: (visits.get(value, 0), parse_appointment_date(value)))

        def allowed(date: str, hour: str, target: str = target) -> bool:
            return date == target and (hour == "00:00" or [date, hour] not in captured)

        progress["session_queries"] += 1
        with evidence_appointment_review(allowed):
            _select_collection_date(page, target, timeout)
            _ensure_live_collection(page)
            result = select_available_appointment(
                page, allow_hidden=True, include_person=False,
                is_allowed_appointment=allowed, timeout=timeout,
            )
        _ensure_live_collection(page)
        if result.status == "available":
            capture(result)
            update_completed(target)
        elif result.status not in {"unavailable", "partial"}:
            raise RuntimeError(result.message)
        visits[target] = visits.get(target, 0) + 1
