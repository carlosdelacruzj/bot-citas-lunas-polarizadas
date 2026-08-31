from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.core.models import AvailabilityResult
from appointment_bot.reservation_engine.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
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
    page,
    settings: Settings,
    result: AvailabilityResult,
    *,
    phase: str,
) -> tuple[AvailabilityResult, Path, Path]:
    details = dict(result.details or {})
    date_text = str(details.get("fecha") or "").strip()
    hour_text = str(details.get("hora") or "").strip()
    if not date_text or not hour_text:
        raise CanonicalSlotCaptureError(
            "No se puede capturar un cupo sin fecha y hora exactas."
        )

    source_path = save_available_appointment_snapshot(page, settings)
    if source_path is None:
        raise CanonicalSlotCaptureError(
            "No se pudo guardar la captura del cupo seleccionado."
        )
    archived_path = archive_unique_slot_capture(settings, details, source_path)
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
        dict(item)
        for item in details.get("_unique_slot_evidence", [])
        if isinstance(item, dict)
    ]
    candidate = {
        "sede": str(details.get("sede") or ""),
        "fecha": date_text,
        "hora": hour_text,
        "screenshot_path": str(source_path),
        "capture_phase": phase,
    }
    if not any(
        item.get("fecha") == date_text and item.get("hora") == hour_text
        for item in evidence
    ):
        evidence.append(candidate)
    details["canonical_slot_capture"] = capture
    details["_unique_slot_evidence"] = evidence
    return replace(result, details=details), source_path, archived_path


def save_available_appointment_snapshot(page, settings: Settings) -> Path | None:
    label = "03-modal-reserva-citas-cupo-disponible"
    path = save_revealed_centered_modal_screenshot(
        page,
        settings,
        label,
        APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    )
    if path is not None:
        return path
    logger.warning("Falling back to a full-page screenshot for available appointment")
    return save_screenshot(page, settings, label)
