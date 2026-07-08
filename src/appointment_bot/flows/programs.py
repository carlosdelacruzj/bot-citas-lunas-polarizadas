from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.flows.appointments import (
    RESERVE_APPOINTMENT_SELECTOR,
    AppointmentWorkflowUnavailable,
)

logger = logging.getLogger(__name__)

PROGRAM_ACTION_SELECTOR = (
    'input[type="image"][onclick*="__doPostBack"][onclick*="gvProgramacion"][onclick*="accion$0"], '
    'a[id^="MainContent_gvProgramacion_btnAccion_"][href*="__doPostBack"], '
    'a[href*="gvProgramacion"][href*="btnAccion"]'
)
def click_program_action(
    page: Page,
    *,
    on_multiple_programs: Callable[[dict[str, Any]], None] | None = None,
) -> Page:
    logger.info("Clicking program action button")
    button = page.locator(PROGRAM_ACTION_SELECTOR)
    button_count = button.count()
    logger.info("Program action buttons found: %s", button_count)

    if button_count == 0:
        raise AppointmentWorkflowUnavailable(
            "No se encontro una accion de programacion disponible. "
            "Es posible que la cita ya este reservada o que ya no exista un flujo pendiente."
        )

    if button_count == 1:
        selected_button = button.first
    else:
        program_rows = _read_program_action_rows(page)
        pending_rows = [
            row for row in program_rows if str(row.get("status") or "").casefold() == "pendiente"
        ]
        multiple_details = {
            "program_count": button_count,
            "pending_count": len(pending_rows),
            "rows": program_rows,
        }

        if len(pending_rows) == 1:
            multiple_details["decision"] = "single_pending_selected"
            multiple_details["selected_row"] = pending_rows[0]
            if on_multiple_programs is not None:
                on_multiple_programs(multiple_details)
            selected_button = button.nth(int(pending_rows[0]["action_index"]))
            logger.info(
                "Multiple program actions found; selecting the only pending program: %s",
                pending_rows[0],
            )
        elif len(pending_rows) > 1:
            multiple_details["decision"] = "multiple_pending_first_selected"
            multiple_details["selected_row"] = pending_rows[0]
            if on_multiple_programs is not None:
                on_multiple_programs(multiple_details)
            selected_button = button.nth(int(pending_rows[0]["action_index"]))
            logger.info(
                "Multiple pending program actions found; selecting the first pending program: %s",
                pending_rows[0],
            )
        else:
            multiple_details["decision"] = "no_pending_blocked"
            if on_multiple_programs is not None:
                on_multiple_programs(multiple_details)
            raise AppointmentWorkflowUnavailable(
                "Hay varios tramites programables, pero ninguno figura como PENDIENTE."
            )

    selected_button.scroll_into_view_if_needed(timeout=15_000)

    selected_button.click(timeout=15_000)
    _wait_for_program_detail(page)
    logger.info("Current page after program action: %s", page.url)
    return page


def _read_program_action_rows(page: Page) -> list[dict[str, Any]]:
    try:
        rows = page.evaluate(
            """selector => {
                const normalize = text => (text || "").replace(/\\s+/g, " ").trim();
                const headers = Array.from(document.querySelectorAll("table tr"))
                    .map(row => Array.from(row.querySelectorAll("th"))
                        .map(cell => normalize(cell.innerText)))
                    .find(items => items.length) || [];
                const actionRows = [];
                Array.from(document.querySelectorAll("table tr")).forEach(row => {
                    if (!row.querySelector(selector)) return;
                    const cells = Array.from(row.querySelectorAll("td"))
                        .map(cell => normalize(cell.innerText));
                    const byHeader = {};
                    headers.forEach((header, index) => {
                        if (header) byHeader[header.toLowerCase()] = cells[index] || "";
                    });
                    const status = cells.find(
                        cell => /^(PENDIENTE|ATENDIDO|CANCELADO)$/i.test(cell)
                    ) || "";
                    actionRows.push({
                        action_index: actionRows.length,
                        expediente: byHeader["expediente"] || cells[0] || "",
                        motivo: byHeader["motivo"] || "",
                        tipo: byHeader["tipo"] || "",
                        placa: byHeader["placa"] || "",
                        marca: byHeader["marca"] || "",
                        modelo: byHeader["modelo"] || "",
                        motor: byHeader["motor"] || "",
                        color: byHeader["color"] || "",
                        status: status,
                        cells: cells
                    });
                });
                return actionRows;
            }""",
            PROGRAM_ACTION_SELECTOR,
        )
    except PlaywrightError as exc:
        logger.warning("Could not read program action rows: %s", exc)
        return []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _wait_for_program_detail(page: Page) -> None:
    try:
        page.wait_for_load_state("load", timeout=10_000)
    except PlaywrightTimeoutError:
        logger.info("Program detail page did not reach load state; checking detail selector")

    try:
        page.locator(RESERVE_APPOINTMENT_SELECTOR).wait_for(state="visible", timeout=5_000)
        return
    except PlaywrightTimeoutError:
        logger.info("Reserve button is not visible; checking process stages table")

    try:
        page.get_by_text("Separa Cita Peritaje").wait_for(state="visible", timeout=15_000)
        return
    except PlaywrightTimeoutError:
        logger.info("Process stages table was not detected by Separa Cita Peritaje text")

    try:
        page.get_by_text("Ingresa Solicitud").wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeoutError as exc:
        raise AppointmentWorkflowUnavailable(
            "No se encontro el detalle del tramite despues de hacer click. "
            "Es posible que la cita ya este reservada o que ya no exista un flujo pendiente."
        ) from exc


