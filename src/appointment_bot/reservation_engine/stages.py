from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.core.models import AvailabilityResult
from appointment_bot.utils.sanitization import normalize_option

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessStage:
    stage: str
    date: str
    status: str
    message: str


def read_process_stages(page: Page) -> list[ProcessStage]:
    logger.info("Reading process stages")
    stages = page.evaluate(
        r"""() => {
            const normalize = value => (value || "").replace(/\s+/g, " ").trim();
            const tables = Array.from(document.querySelectorAll("table"));
            const table = tables.find(candidate => {
                const text = normalize(candidate.innerText);
                return text.includes("Separa Cita Peritaje")
                    || text.includes("Ingresa Solicitud");
            });
            if (!table) return [];

            return Array.from(table.querySelectorAll("tr")).map(row => {
                const cells = Array.from(row.querySelectorAll("td"));
                return cells.map(cell => normalize(cell.innerText));
            }).filter(cells => cells.length >= 3).map(cells => ({
                stage: cells[0] || "",
                date: cells[1] || "",
                status: cells[2] || "",
                message: cells[3] || "",
            }));
        }"""
    )
    return [
        ProcessStage(
            stage=str(stage.get("stage") or ""),
            date=str(stage.get("date") or ""),
            status=str(stage.get("status") or ""),
            message=str(stage.get("message") or ""),
        )
        for stage in stages
    ]


def appointment_stage_result(stages: list[ProcessStage]) -> AvailabilityResult | None:
    appointment_stage = next(
        (stage for stage in stages if stage.stage.strip().lower() == "separa cita peritaje"),
        None,
    )
    if appointment_stage is None:
        logger.warning("Could not find Separa Cita Peritaje stage")
        return AvailabilityResult(
            status="unknown",
            message=(
                "No se pudo identificar la etapa Separa Cita Peritaje. "
                "La reserva se detuvo para evitar una accion duplicada."
            ),
        )

    normalized_status = appointment_stage.status.strip().lower()
    details = {
        "etapa": appointment_stage.stage,
        "estado": appointment_stage.status,
    }
    if appointment_stage.date:
        details["fecha"] = appointment_stage.date
    if appointment_stage.message:
        details["mensaje"] = appointment_stage.message

    if normalized_status in {"programado", "atendido"}:
        return AvailabilityResult(
            status="completed",
            message=(
                f"La etapa Separa Cita Peritaje ya esta en estado {appointment_stage.status}. "
                "No hay una cita pendiente por reservar."
            ),
            details=details,
        )
    if normalized_status == "pendiente":
        return None
    return AvailabilityResult(
        status="unknown",
        message=(
            "La etapa Separa Cita Peritaje tiene un estado no reconocido para este flujo. "
            f"Estado actual: {appointment_stage.status}. Requiere revision manual."
        ),
        details=details,
    )


def wait_for_programmed_appointment_stage(
    page: Page,
    expected_details: dict[str, str] | None,
    *,
    timeout: int = 15_000,
) -> ProcessStage | None:
    expected_details = expected_details or {}
    expected_date = normalize_option(expected_details.get("fecha", ""))
    expected_hour = normalize_option(expected_details.get("hora", ""))
    deadline = time.monotonic() + timeout / 1_000
    mismatch_logged = False

    while time.monotonic() < deadline:
        try:
            stages = read_process_stages(page)
        except PlaywrightError:
            page.wait_for_timeout(500)
            continue
        stage = next(
            (
                item
                for item in stages
                if item.stage.strip().lower() == "separa cita peritaje"
                and item.status.strip().lower() == "programado"
            ),
            None,
        )
        if stage is not None:
            programmed_text = normalize_option(f"{stage.date} {stage.message}")
            date_matches = not expected_date or expected_date in programmed_text
            hour_matches = not expected_hour or expected_hour in programmed_text
            if not date_matches or not hour_matches:
                if not mismatch_logged:
                    logger.warning(
                        "Programmed stage differs from selected appointment: "
                        "expected %s %s, got %s",
                        expected_date,
                        expected_hour,
                        programmed_text,
                    )
                    mismatch_logged = True
                page.wait_for_timeout(500)
                continue
            return stage
        page.wait_for_timeout(500)

    logger.info("Programmed appointment stage was not confirmed before timeout")
    return None
