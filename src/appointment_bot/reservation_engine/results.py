from __future__ import annotations

from dataclasses import replace

from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult, RunReport
from appointment_bot.reports.run_reporting import reservation_confirmed
from appointment_bot.utils.screenshots import remove_screenshot_paths, report_screenshot_paths


def cleanup_unconfirmed_session_screenshots(report: RunReport) -> None:
    if reservation_confirmed(report) or report.status in {
        "error",
        "unknown",
        "reservation_unconfirmed",
    }:
        return
    details = report.details or {}
    artifacts = details.get("diagnostic_artifacts")
    if details.get("captcha_attempts") or (
        isinstance(artifacts, dict) and artifacts.get("captcha_images")
    ):
        return
    if report.status == "partial" and has_partial_availability_evidence(details):
        return

    remove_screenshot_paths(report_screenshot_paths(report))


def with_client_context(
    result: AvailabilityResult,
    *,
    order_id: str | None,
    client_name: str | None,
    settings: Settings,
    program_expediente: str | None = None,
    program_plate: str | None = None,
) -> AvailabilityResult:
    if order_id is None:
        return result

    details = dict(result.details or {})
    details.setdefault("orden", order_id)
    details.setdefault("cuenta", settings.safe_username)
    if program_expediente:
        details.setdefault("program_expediente", program_expediente)
    if program_plate:
        details.setdefault("program_plate", program_plate)
    if client_name:
        details.setdefault("cliente", client_name)
    return replace(result, details=details)


def has_partial_availability_evidence(details: dict) -> bool:
    date_text = str(details.get("fecha") or details.get("appointment_date") or "").strip()
    hour_text = str(details.get("hora") or details.get("appointment_hour") or "").strip()
    if bool(details.get("blocked_by_order_rule")) or bool(
        details.get("blocked_selected_for_evidence")
    ):
        return True
    if date_text and date_text.casefold() != "sin cupos":
        return True
    return bool(hour_text and hour_text.casefold() != "sin cupos")
