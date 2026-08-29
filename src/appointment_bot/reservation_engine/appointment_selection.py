from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.core.models import AvailabilityResult
from appointment_bot.core.rules import parse_appointment_date, parse_appointment_time
from appointment_bot.reservation_engine.appointment_reader import (
    read_atomic_appointment_snapshot,
    read_stable_appointment_snapshot,
    snapshot_details,
)

logger = logging.getLogger(__name__)

IDENTITY_READ_ATTEMPTS = 3
IDENTITY_READ_RETRY_MS = 150
_MASKED_IDENTITY_VALUES = {"", "***", "usuario oculto"}
EVENT_SIGNAL_TIMEOUT_MS = 750
EVENT_STABLE_INTERVAL_MS = 150


def _start_selection_stability_probe(page: Page) -> str | None:
    try:
        return page.evaluate(
            """() => {
                const token = `${Date.now()}-${Math.random()}`;
                window.__appointmentBotSelectionProbes =
                    window.__appointmentBotSelectionProbes || {};
                const probe = {
                    startedAt: performance.now(),
                    changedAt: performance.now(),
                    changeSeen: false,
                    mutationCount: 0,
                    asyncCompleted: false,
                    observer: null,
                    asyncHandler: null,
                    changeHandler: null,
                };
                probe.changeHandler = () => {
                    probe.changeSeen = true;
                    probe.changedAt = performance.now();
                };
                for (const selector of [
                    "#MainContent_idUcitas_cboFecha",
                    "#MainContent_idUcitas_cboHora",
                ]) {
                    document.querySelector(selector)?.addEventListener(
                        "change", probe.changeHandler
                    );
                }
                const root = document.querySelector("#MainContent_idUcitas")
                    || document.body;
                probe.observer = new MutationObserver(() => {
                    probe.mutationCount += 1;
                    probe.changedAt = performance.now();
                });
                probe.observer.observe(root, {
                    attributes: true,
                    childList: true,
                    characterData: true,
                    subtree: true,
                });
                try {
                    const prm = window.Sys?.WebForms?.PageRequestManager?.getInstance();
                    if (prm) {
                        probe.asyncHandler = () => {
                            probe.asyncCompleted = true;
                            probe.changedAt = performance.now();
                        };
                        prm.add_endRequest(probe.asyncHandler);
                    }
                } catch (error) {}
                window.__appointmentBotSelectionProbes[token] = probe;
                return token;
            }"""
        )
    except PlaywrightError:
        return None


def _stop_selection_stability_probe(page: Page, token: str | None) -> None:
    if not token:
        return
    try:
        page.evaluate(
            """token => {
                const probes = window.__appointmentBotSelectionProbes || {};
                const probe = probes[token];
                if (!probe) return;
                try { probe.observer?.disconnect(); } catch (error) {}
                for (const selector of [
                    "#MainContent_idUcitas_cboFecha",
                    "#MainContent_idUcitas_cboHora",
                ]) {
                    try {
                        document.querySelector(selector)?.removeEventListener(
                            "change", probe.changeHandler
                        );
                    } catch (error) {}
                }
                try {
                    const prm = window.Sys?.WebForms?.PageRequestManager?.getInstance();
                    if (prm && probe.asyncHandler) {
                        prm.remove_endRequest(probe.asyncHandler);
                    }
                } catch (error) {}
                delete probes[token];
            }""",
            token,
        )
    except PlaywrightError:
        pass


def _wait_for_selected_appointment_stability(
    page: Page,
    *,
    expected_date: str,
    expected_hour: str,
    include_person: bool,
    event_driven: bool,
    probe_token: str | None = None,
) -> tuple[object, dict[str, Any]]:
    started = time.monotonic()
    fallback_reason: str | None = None
    if event_driven and probe_token is None:
        probe_token = _start_selection_stability_probe(page)
    if event_driven and probe_token is not None:
        try:
            page.wait_for_function(
                """expected => {
                    const probe = window.__appointmentBotSelectionProbes?.[expected.token];
                    if (!probe || !probe.changeSeen) return false;
                    const selectedText = selector => {
                        const element = document.querySelector(selector);
                        const option = element?.options?.[element.selectedIndex];
                        return (option?.innerText || "").trim().toLowerCase();
                    };
                    let asyncActive = false;
                    try {
                        asyncActive = Boolean(
                            window.Sys?.WebForms?.PageRequestManager?.getInstance()
                                ?.get_isInAsyncPostBack()
                        );
                    } catch (error) {}
                    const targetSelected =
                        selectedText("#MainContent_idUcitas_cboFecha")
                            === expected.date.trim().toLowerCase()
                        && selectedText("#MainContent_idUcitas_cboHora")
                            === expected.hour.trim().toLowerCase();
                    const quietFor = performance.now() - probe.changedAt;
                    return targetSelected && !asyncActive && quietFor >= 100
                        && (probe.asyncCompleted || probe.mutationCount > 0
                            || performance.now() - probe.startedAt >= 150);
                }""",
                arg={
                    "token": probe_token,
                    "date": expected_date,
                    "hour": expected_hour,
                },
                timeout=EVENT_SIGNAL_TIMEOUT_MS,
                polling=50,
            )
            first_snapshot = read_atomic_appointment_snapshot(page)
            page.wait_for_timeout(EVENT_STABLE_INTERVAL_MS)
            second_snapshot = read_atomic_appointment_snapshot(page)
            if (
                first_snapshot.signature() == second_snapshot.signature()
                and _same_selection_option(second_snapshot.date, expected_date)
                and _same_selection_option(second_snapshot.hour, expected_hour)
            ):
                return second_snapshot, {
                    "mode": "event_atomic",
                    "signal_seconds": round(
                        max(time.monotonic() - started, 0.0), 3
                    ),
                    "fallback_reason": None,
                    "atomic_snapshots": 2,
                }
            fallback_reason = "atomic_snapshots_not_stable"
        except PlaywrightTimeoutError:
            fallback_reason = "event_signal_timeout"
        except Exception as exc:
            fallback_reason = f"event_probe_error:{type(exc).__name__}"
        finally:
            _stop_selection_stability_probe(page, probe_token)
    elif event_driven:
        fallback_reason = "event_probe_unavailable"
    else:
        fallback_reason = "feature_disabled"

    fallback_started = time.monotonic()
    elapsed_ms = (fallback_started - started) * 1_000
    remaining_legacy_wait_ms = max(0, round(500 - elapsed_ms))
    if remaining_legacy_wait_ms:
        page.wait_for_timeout(remaining_legacy_wait_ms)
    snapshot = read_stable_appointment_snapshot(page, log_person=include_person)
    return snapshot, {
        "mode": "legacy_fallback" if event_driven else "legacy",
        "signal_seconds": round(max(fallback_started - started, 0.0), 3),
        "fallback_seconds": round(max(time.monotonic() - fallback_started, 0.0), 3),
        "fallback_reason": fallback_reason,
        "legacy_wait_ms": remaining_legacy_wait_ms,
        "atomic_snapshots": 0,
    }


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


def _same_selection_option(actual: str, expected: str) -> bool:
    from appointment_bot.utils.sanitization import normalize_option

    return normalize_option(actual) == normalize_option(expected)


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
        "observed_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "date_postback_seconds": [],
        "hour_stabilization_seconds": [],
        "hour_stabilization_modes": [],
        "hour_signal_seconds": [],
        "hour_fallback_seconds": [],
        "hour_fallback_reasons": [],
        "hour_atomic_snapshot_counts": [],
        "observed_appointments": [],
    }
    logger.info("Selecting available appointment date and hour")
    options_started = time.monotonic()
    date_options = sorted(
        _real_options(_select_options(page, DATE_SELECTOR)),
        key=_date_option_sort_key,
    )
    observation["date_options_read_seconds"] = round(time.monotonic() - options_started, 3)
    observation["date_candidate_count"] = len(date_options)
    observation["visible_dates"] = [str(option["text"]) for option in date_options]
    if not date_options:
        raise AppointmentWorkflowUnavailable(
            "Se detecto disponibilidad, pero no se encontro una fecha seleccionable."
        )

    blocked_evidence_candidate: dict[str, str] | None = None
    for date_option in date_options:
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
        for hour_option in sorted(real_hour_options, key=_hour_option_sort_key):
            _remember_observed_appointment(
                observation,
                date_text=str(date_option["text"]),
                hour_text=str(hour_option["text"]),
            )
        observation["hour_candidate_count"] = observation.get("hour_candidate_count", 0) + len(
            real_hour_options
        )
        if not real_hour_options:
            logger.info("No selectable hours found for date %s", date_option["text"])
            continue

        for hour_option in sorted(real_hour_options, key=_hour_option_sort_key):
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
            probe_token = _start_selection_stability_probe(page)
            try:
                _select_appointment_option(
                    hour_select,
                    hour_option["value"],
                    allow_hidden=allow_hidden,
                )
            except Exception:
                _stop_selection_stability_probe(page, probe_token)
                raise
            stabilization_started = time.monotonic()
            snapshot, stability = _wait_for_selected_appointment_stability(
                page,
                expected_date=str(date_option["text"]),
                expected_hour=str(hour_option["text"]),
                include_person=include_person,
                event_driven=True,
                probe_token=probe_token,
            )
            observation["hour_stabilization_seconds"].append(
                round(time.monotonic() - stabilization_started, 3)
            )
            observation["hour_stabilization_modes"].append(stability["mode"])
            observation["hour_signal_seconds"].append(stability.get("signal_seconds"))
            observation["hour_fallback_seconds"].append(
                stability.get("fallback_seconds")
            )
            observation["hour_fallback_reasons"].append(
                stability.get("fallback_reason")
            )
            observation["hour_atomic_snapshot_counts"].append(
                stability.get("atomic_snapshots")
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

        probe_token = _start_selection_stability_probe(page)
        try:
            _select_appointment_option(
                page.locator(HOUR_SELECTOR),
                str(matching_hour["value"]),
                allow_hidden=allow_hidden,
            )
        except Exception:
            _stop_selection_stability_probe(page, probe_token)
            raise
        stabilization_started = time.monotonic()
        snapshot, stability = _wait_for_selected_appointment_stability(
            page,
            expected_date=date_text,
            expected_hour=hour_text,
            include_person=include_person,
            event_driven=True,
            probe_token=probe_token,
        )
        observation["hour_stabilization_seconds"].append(
            round(time.monotonic() - stabilization_started, 3)
        )
        observation["hour_stabilization_modes"].append(stability["mode"])
        observation["hour_signal_seconds"].append(stability.get("signal_seconds"))
        observation["hour_fallback_seconds"].append(stability.get("fallback_seconds"))
        observation["hour_fallback_reasons"].append(stability.get("fallback_reason"))
        observation["hour_atomic_snapshot_counts"].append(
            stability.get("atomic_snapshots")
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


def _remember_observed_appointment(
    observation: dict[str, Any],
    *,
    date_text: str,
    hour_text: str,
) -> None:
    appointments = observation.setdefault("observed_appointments", [])
    candidate = {"date": date_text, "hour": hour_text}
    if candidate not in appointments:
        appointments.append(candidate)


def _date_option_sort_key(option: dict[str, Any]) -> tuple[bool, date]:
    parsed = parse_appointment_date(str(option.get("text") or ""))
    return parsed is None, parsed or date.max


def _hour_option_sort_key(option: dict[str, Any]) -> tuple[bool, tuple[int, int]]:
    parsed = parse_appointment_time(str(option.get("text") or ""))
    return parsed is None, parsed or (24, 0)


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
) -> dict[str, Any]:
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
    started = time.monotonic()
    mode = "atomic"
    fallback_reason: str | None = None
    try:
        snapshot = read_atomic_appointment_snapshot(page)
        actual_site = snapshot.site
        actual_date = snapshot.date
        actual_hour = snapshot.hour
        actual_slots = snapshot.slots
        if (
            (expected_site and not actual_site)
            or (expected_date and not actual_date)
            or (expected_hour and not actual_hour)
        ):
            raise ValueError("atomic_snapshot_missing_expected_selection")
    except Exception as exc:
        fallback_reason = f"atomic_error:{type(exc).__name__}"
        logger.warning(
            "Atomic appointment validation fell back to legacy reads: %s",
            fallback_reason,
        )
        actual_site = _selected_option_text(page, SITE_SELECTOR)
        actual_date = _selected_option_text(page, DATE_SELECTOR)
        actual_hour = _selected_option_text(page, HOUR_SELECTOR)
        actual_slots = _read_slots_value(page)
        mode = "legacy_fallback"
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
    return {
        "mode": mode,
        "fallback_reason": fallback_reason,
        "duration_ms": round(max(time.monotonic() - started, 0.0) * 1_000, 3),
    }
