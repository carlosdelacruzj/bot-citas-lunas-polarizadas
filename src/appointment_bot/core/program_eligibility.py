from __future__ import annotations

import re
from typing import Any


class ProgramHistoryUnresolved(ValueError):
    def __init__(self, reservation_ids: list[str]) -> None:
        self.reservation_ids = reservation_ids
        super().__init__(
            "Hay reservas confirmadas sin expediente inequívoco en esta cuenta. "
            "Requiere conciliar el historial antes de buscar otra cita."
        )


def reservation_program_identity(record: dict[str, Any]) -> str:
    details = record.get("details_json") or {}
    candidates = [record.get("program_expediente"), details.get("program_expediente")]
    identities = {
        program_key(value): str(value).strip() for value in candidates if program_key(value)
    }
    return next(iter(identities.values())) if len(identities) == 1 else ""


def appointment_identity(date: object, hour: object = "", message: object = "") -> tuple[str, str]:
    text = f"{date or ''} {hour or ''} {message or ''}"
    dates = set(re.findall(r"\b\d{2}/\d{2}/\d{4}\b", text))
    hours = set(re.findall(r"\b\d{2}:\d{2}\b", text))
    if len(dates) != 1 or len(hours) != 1:
        return "", ""
    return next(iter(dates)), next(iter(hours))


def program_key(value: object) -> str:
    return "".join(str(value or "").split()).casefold()


def program_is_eligible(row: dict[str, Any]) -> bool:
    return (
        program_key(row.get("status")) == "pendiente"
        and bool(program_key(row.get("expediente")))
        and row.get("eligibility") == "eligible"
    )


def classify_appointment_stage(
    *, status: str, date: str = "", message: str = ""
) -> dict[str, Any]:
    normalized = program_key(status)
    if normalized in {"programado", "atendido"}:
        eligibility, reason = "booked", "Cita ya reservada; excluido de nuevas búsquedas."
    elif normalized == "pendiente" and not date.strip() and not message.strip():
        eligibility, reason = "eligible", "Sin cita asignada en el portal."
    else:
        eligibility, reason = "unknown", "No se pudo descartar una cita previa; requiere revisión."
    return {
        "eligibility": eligibility,
        "eligibility_reason": reason,
        "appointment_source": "portal",
        "appointment_status": status,
        "appointment_date": date,
        "appointment_message": message,
    }
