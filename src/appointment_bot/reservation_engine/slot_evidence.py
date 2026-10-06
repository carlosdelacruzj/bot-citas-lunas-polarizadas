from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.core.models import AvailabilityResult
from appointment_bot.reservation_engine.appointment_contracts import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    DATE_SELECTOR,
    HOUR_SELECTOR,
    SITE_SELECTOR,
    SLOTS_LABEL_ID,
)
from appointment_bot.utils.screenshots import (
    archive_unique_slot_capture,
    save_revealed_centered_modal_screenshot,
    save_screenshot,
)

logger = logging.getLogger(__name__)


class CanonicalSlotCaptureError(RuntimeError):
    pass


def capture_canonical_selected_slot(
    page, result: AvailabilityResult, *, evidence_settings: EvidenceSettings, phase: str
) -> tuple[AvailabilityResult, Path, Path]:
    details = dict(result.details or {})
    date_text = str(details.get("fecha") or "").strip()
    hour_text = str(details.get("hora") or "").strip()
    if not date_text or not hour_text:
        raise CanonicalSlotCaptureError("No se puede capturar un cupo sin fecha y hora exactas.")

    try:
        details["cupos"] = _wait_for_visible_selected_slot(page, details)
    except PlaywrightError as exc:
        save_screenshot(page, "cupo-modal-incompleto", evidence_settings=evidence_settings)
        raise CanonicalSlotCaptureError(
            "El modal no mostro la seleccion exacta, cupos positivos y boton habilitado "
            "de forma estable; no se guardo como evidencia de disponibilidad."
        ) from exc

    source_path = save_available_appointment_snapshot(page, evidence_settings=evidence_settings)
    if source_path is None:
        raise CanonicalSlotCaptureError("No se pudo guardar la captura del cupo seleccionado.")
    archived_path = archive_unique_slot_capture(
        details, source_path, evidence_settings=evidence_settings
    )
    if archived_path is None:
        raise CanonicalSlotCaptureError(
            "No se pudo archivar la captura canonica del cupo seleccionado."
        )

    capture = {
        "phase": phase,
        "date": date_text,
        "hour": hour_text,
        "source_path": str(source_path),
        "archived_path": str(archived_path),
        "captured_before_captcha": True,
    }
    evidence = [
        dict(item) for item in details.get("_unique_slot_evidence", []) if isinstance(item, dict)
    ]
    candidate = {
        "sede": str(details.get("sede") or ""),
        "fecha": date_text,
        "hora": hour_text,
        "screenshot_path": str(source_path),
        "capture_phase": phase,
    }
    if not any(
        item.get("fecha") == date_text and item.get("hora") == hour_text for item in evidence
    ):
        evidence.append(candidate)
    details["canonical_slot_capture"] = capture
    details["_unique_slot_evidence"] = evidence
    return replace(result, details=details), source_path, archived_path


def _wait_for_visible_selected_slot(page, details: dict) -> str:
    page.evaluate("delete window.__canonicalSlotReady")
    handle = page.wait_for_function(
        r"""expected => {
            const visible = element => element && element.checkVisibility({
                checkOpacity: true, checkVisibilityCSS: true
            });
            const selected = selector => {
                const element = document.querySelector(selector);
                return visible(element)
                    ? (element.selectedOptions[0]?.textContent || '').trim() : '';
            };
            const slots = document.getElementById(expected.slotsId);
            const count = (slots?.textContent || '').trim();
            const button = document.querySelector('#MainContent_idUcitas_btgSiguiente');
            const manager = window.Sys?.WebForms?.PageRequestManager?.getInstance();
            const loading = manager?.get_isInAsyncPostBack()
                || Array.from(document.querySelectorAll('[id*="UpdateProgress"]'))
                    .some(visible);
            const ready = !loading && visible(slots) && /^\d+$/.test(count)
                && Number(count) > 0 && visible(button) && !button.disabled
                && selected(expected.dateSelector) === expected.date
                && selected(expected.hourSelector) === expected.hour
                && (!expected.site || selected(expected.siteSelector) === expected.site);
            const signature = ready ? [expected.date, expected.hour, count].join('|') : '';
            const previous = window.__canonicalSlotReady;
            if (!signature || previous?.signature !== signature) {
                window.__canonicalSlotReady = {signature, since: performance.now()};
                return false;
            }
            return performance.now() - previous.since >= 150 ? count : false;
        }""",
        arg={
            "dateSelector": DATE_SELECTOR,
            "hourSelector": HOUR_SELECTOR,
            "siteSelector": SITE_SELECTOR,
            "slotsId": SLOTS_LABEL_ID,
            "date": str(details["fecha"]).strip(),
            "hour": str(details["hora"]).strip(),
            "site": str(details.get("sede") or "").strip(),
        },
        polling=50,
        timeout=5000,
    )
    try:
        return str(handle.json_value())
    finally:
        handle.dispose()


def save_available_appointment_snapshot(
    page, *, evidence_settings: EvidenceSettings
) -> Path | None:
    label = "03-modal-reserva-citas-cupo-disponible"
    path = save_revealed_centered_modal_screenshot(
        page, label, APPOINTMENT_PANEL_SCREENSHOT_SELECTORS, evidence_settings=evidence_settings
    )
    if path is not None:
        return path
    logger.warning("Falling back to a full-page screenshot for available appointment")
    return save_screenshot(page, label, evidence_settings=evidence_settings)
