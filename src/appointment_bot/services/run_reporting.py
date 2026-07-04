from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.domain import (
    AvailabilityResult,
    ResultStatus,
    RunReport,
    sanitize_details,
)
from appointment_bot.services.evidence_summary import append_evidence_case
from appointment_bot.services.optimization_log import (
    append_optimization_case,
    append_partial_availability_case,
)
from appointment_bot.services.postgres_database import (
    RunRecord,
    record_run_outcome,
)
from appointment_bot.utils.sanitization import sanitize_text
from appointment_bot.utils.screenshots import normalize_screenshot_paths

logger = logging.getLogger(__name__)


def report_from_result(
    result: AvailabilityResult,
    *,
    exit_code: int | None = None,
    run_id: str | None = None,
    order_id: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    duration_seconds: float | None = None,
    screenshot_path: Path | None = None,
    screenshot_paths: list[Path] | None = None,
) -> RunReport:
    all_screenshot_paths = normalize_screenshot_paths(screenshot_path, screenshot_paths)
    effective_exit_code = (
        1
        if result.status
        in {ResultStatus.ERROR, ResultStatus.UNKNOWN, ResultStatus.RESERVATION_UNCONFIRMED}
        else 0
    )
    if exit_code is not None:
        effective_exit_code = exit_code
    return RunReport(
        status=result.status,
        message=result.message,
        exit_code=effective_exit_code,
        run_id=run_id,
        order_id=order_id,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        reservation_attempted=(
            result.status in {ResultStatus.REGISTERED, ResultStatus.RESERVATION_UNCONFIRMED}
            or bool((result.details or {}).get("submission_outcome"))
        ),
        reservation_confirmed=result.status == ResultStatus.REGISTERED,
        details=result.details,
        screenshot_path=str(all_screenshot_paths[0]) if all_screenshot_paths else None,
        screenshot_paths=[str(path) for path in all_screenshot_paths] or None,
    )


def settings_for_order(settings: Settings, *, username: str, password: str) -> Settings:
    return replace(settings, login_username=username, login_password=password)


def reservation_confirmed(report: RunReport) -> bool:
    if report.status == ResultStatus.REGISTERED or report.reservation_confirmed:
        return True
    if _programmed_stage_confirmed(report):
        return True
    return False


def finalize_report(
    report: RunReport,
    settings: Settings,
    *,
    started_at_dt: datetime,
) -> RunReport:
    finished_at_dt = datetime.now(UTC)
    confirmed = reservation_confirmed(report)
    finalized = replace(
        report,
        finished_at=finished_at_dt.isoformat(timespec="seconds"),
        duration_seconds=round((finished_at_dt - started_at_dt).total_seconds(), 3),
        reservation_attempted=report.reservation_attempted or confirmed,
        reservation_confirmed=confirmed,
    )
    if finalized.run_id is not None:
        record_run_history(settings, finalized)
    return finalized


def record_run_history(settings: Settings, report: RunReport) -> None:
    screenshot_paths = report.screenshot_paths or []
    if report.screenshot_path and report.screenshot_path not in screenshot_paths:
        screenshot_paths = [report.screenshot_path, *screenshot_paths]
    try:
        person_name = str((report.details or {}).get("nombre") or "").strip() or None
        record_run_outcome(
            settings,
            RunRecord(
                run_id=report.run_id or "",
                order_id=report.order_id,
                status=report.status,
                message=sanitize_text(report.message),
                exit_code=report.exit_code,
                started_at=report.started_at or "",
                finished_at=report.finished_at or "",
                duration_seconds=report.duration_seconds or 0,
                reservation_attempted=report.reservation_attempted,
                reservation_confirmed=report.reservation_confirmed,
                details=sanitize_details(report.details),
                screenshot_path=report.screenshot_path,
            ),
            screenshot_paths=screenshot_paths,
            report=report,
            person_name=person_name,
            include_reservation=_report_should_record_reservation(report),
        )
    except Exception as exc:
        if reservation_confirmed(report):
            raise
        logger.warning("Could not record run history: %s", exc)
        return
    try:
        append_optimization_case(report)
    except Exception as exc:
        logger.warning("Could not append optimization log entry: %s", exc)
    try:
        append_partial_availability_case(report)
    except Exception as exc:
        logger.warning("Could not append partial availability log entry: %s", exc)
    try:
        append_evidence_case(report)
    except Exception as exc:
        logger.warning("Could not append evidence summary entry: %s", exc)


def _report_should_record_reservation(report: RunReport) -> bool:
    return reservation_confirmed(report)


def _programmed_stage_confirmed(report: RunReport) -> bool:
    if report.status != ResultStatus.COMPLETED:
        return False
    details = report.details or {}
    status = str(details.get("estado") or "").strip().casefold()
    date_text = str(details.get("fecha") or "").strip()
    return status == "programado" and bool(date_text)
