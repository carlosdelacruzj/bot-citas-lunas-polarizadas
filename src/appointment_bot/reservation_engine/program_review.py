from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.core.program_eligibility import classify_appointment_stage, program_key
from appointment_bot.reservation_engine.appointment_contracts import AppointmentWorkflowUnavailable
from appointment_bot.reservation_engine.programs import (
    open_program_detail_for_review,
    read_program_action_rows,
)
from appointment_bot.reservation_engine.stages import read_process_stages


def read_program_appointment(page: Page) -> dict[str, Any]:
    stages = [
        stage for stage in read_process_stages(page)
        if program_key(stage.stage) == "separacitaperitaje"
    ]
    if len(stages) != 1:
        assessment = classify_appointment_stage(status="")
    else:
        stage = stages[0]
        assessment = classify_appointment_stage(
            status=stage.status, date=stage.date, message=stage.message
        )
    return {
        **assessment,
        "appointment_checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def review_programs(
    page: Page,
    rows: list[dict[str, Any]],
    booked: dict[str, dict[str, Any]],
    *,
    on_review: Callable[[list[dict[str, Any]]], None] | None = None,
) -> list[dict[str, Any]]:
    listing_url = page.url
    reviewed = []
    keys = [program_key(row.get("expediente")) for row in rows]
    for index, row in enumerate(rows):
        key = program_key(row.get("expediente"))
        if not key or keys.count(key) != 1:
            raise AppointmentWorkflowUnavailable("El listado no identifica expedientes únicos.")
        if key in booked:
            reviewed.append({**row, **booked[key], "expediente": row["expediente"]})
        elif program_key(row.get("status")) != "pendiente":
            reviewed.append({
                **row, "eligibility": "not_pending",
                "eligibility_reason": "El trámite no figura como PENDIENTE.",
            })
        else:
            try:
                if page.url != listing_url:
                    page.goto(listing_url, wait_until="domcontentloaded", timeout=30_000)
                current = read_program_action_rows(page)
                if _listing_identity(current) != _listing_identity(rows):
                    raise AppointmentWorkflowUnavailable("El listado cambió durante la revisión.")
                open_program_detail_for_review(page, program_expediente=str(row["expediente"]))
                assessment = read_program_appointment(page)
            except (PlaywrightError, AppointmentWorkflowUnavailable):
                reviewed.extend({
                    **remaining, **classify_appointment_stage(status=""),
                    "eligibility_reason": "Consulta interrumpida; requiere volver a validar.",
                    "appointment_checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
                } for remaining in rows[index:])
                return reviewed
            reviewed.append({**row, **assessment})
            if on_review is not None:
                on_review(reviewed)
            # Return to the list even when the portal uses the same URL for both views.
            try:
                page.goto(listing_url, wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightError as exc:
                reviewed.extend({
                    **remaining, **classify_appointment_stage(status=""),
                    "eligibility_reason": "No se pudo volver al listado; requiere revisión.",
                    "appointment_checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
                } for remaining in rows[index + 1:])
                if index == len(rows) - 1:
                    raise AppointmentWorkflowUnavailable(
                        "No se pudo volver al listado verificado."
                    ) from exc
                return reviewed
    return reviewed


def _listing_identity(rows: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    return sorted(
        (program_key(row.get("expediente")), program_key(row.get("placa")),
         program_key(row.get("status")))
        for row in rows
    )
