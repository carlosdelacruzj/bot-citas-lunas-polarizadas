from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from appointment_bot.domain import ResultStatus, RunReport, sanitize_details
from appointment_bot.reservation_engine.timings import TIMING_DETAILS_KEY
from appointment_bot.services.database_models import RunDetail
from appointment_bot.services.detail_helpers import (
    LIMA_TZ,
    detail_text,
    detection_origin,
    format_lima_datetime,
    parse_datetime,
)
from appointment_bot.utils.sanitization import sanitize_text

EVIDENCE_INDEX_PATH = Path("docs/evidence-index.csv")
EVIDENCE_SUMMARY_PATH = Path("docs/evidence-summary.md")
EVIDENCE_STATUSES = {
    ResultStatus.AVAILABLE,
    ResultStatus.PARTIAL,
    ResultStatus.REGISTERED,
    ResultStatus.RESERVATION_UNCONFIRMED,
    ResultStatus.UNKNOWN,
}
SUBMISSION_EVIDENCE_OUTCOMES = {"captcha_invalid", "slot_lost", "rejected", "confirmed"}
DEFENSE_PATTERNS = (
    ("http_429", ("429", "too many requests")),
    ("http_403", ("403", "forbidden")),
    ("access_denied", ("access denied", "acceso denegado")),
    ("unexpected_captcha", ("captcha inesperado", "unexpected captcha")),
    ("session_closed", ("session closed", "sesion cerrada", "session expired")),
    ("network", ("err_network", "network changed", "connection reset", "timeout")),
)
OBSOLETE_CAPTCHA_PANEL_ARTIFACT = "04-reserva-captcha-panel-tecnico-2captcha"
CSV_FIELDS = (
    "run_id",
    "finished_at_lima",
    "order_id",
    "status",
    "detection_origin",
    "site",
    "appointment_date",
    "appointment_hour",
    "slots",
    "submission_outcome",
    "confirmation_source",
    "defense_signal",
    "duration_seconds",
    "total_from_available_seconds",
    "selection_seconds",
    "captcha_solver_seconds",
    "click_to_portal_response_seconds",
    "screenshot_path",
    "evidence_paths",
    "message",
)


@dataclass(frozen=True)
class EvidenceSummaryResult:
    csv_path: Path
    markdown_path: Path
    event_count: int


def append_evidence_case(report: RunReport) -> None:
    row = evidence_row_from_report(report)
    if row is None:
        return
    append_evidence_rows(EVIDENCE_INDEX_PATH, [row])
    write_evidence_summary(EVIDENCE_SUMMARY_PATH, read_evidence_rows(EVIDENCE_INDEX_PATH))


def export_evidence_summary(
    runs: Iterable[RunDetail],
    *,
    output_dir: Path,
    days: int,
    now: datetime | None = None,
    update_current: bool = False,
) -> EvidenceSummaryResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        row
        for run in runs
        if _run_in_days(run, days=days, now=now)
        for row in [evidence_row_from_run_detail(run)]
        if row is not None
    ]
    stamp = datetime.now(LIMA_TZ).strftime("%Y%m%d")
    csv_path = output_dir / f"evidence-events-{stamp}.csv"
    markdown_path = output_dir / f"evidence-summary-{stamp}.md"
    write_evidence_rows(csv_path, rows)
    write_evidence_summary(markdown_path, rows, title=f"Resumen de evidencia - ultimos {days} dias")
    if update_current:
        write_evidence_rows(EVIDENCE_INDEX_PATH, rows)
        write_evidence_summary(EVIDENCE_SUMMARY_PATH, rows)
    return EvidenceSummaryResult(csv_path, markdown_path, len(rows))


def evidence_row_from_run_detail(run: RunDetail) -> dict[str, str] | None:
    return _evidence_row(
        run_id=run.run_id,
        finished_at=run.finished_at,
        order_id=run.order_id,
        status=str(run.status),
        message=run.message,
        duration_seconds=run.duration_seconds,
        reservation_attempted=run.reservation_attempted,
        reservation_confirmed=run.reservation_confirmed,
        details=run.details,
        screenshot_path=run.screenshot_path,
        screenshot_paths=run.screenshot_paths,
    )


def evidence_row_from_report(report: RunReport) -> dict[str, str] | None:
    return _evidence_row(
        run_id=report.run_id or "",
        finished_at=report.finished_at or "",
        order_id=report.order_id,
        status=str(report.status),
        message=report.message,
        duration_seconds=report.duration_seconds,
        reservation_attempted=report.reservation_attempted,
        reservation_confirmed=report.reservation_confirmed,
        details=report.details,
        screenshot_path=report.screenshot_path,
        screenshot_paths=report.screenshot_paths or [],
    )


def append_evidence_rows(path: Path, rows: Iterable[dict[str, str]]) -> None:
    rows = list(rows)
    if not rows:
        return
    existing_ids = _existing_run_ids(path)
    new_rows = [row for row in rows if row.get("run_id") not in existing_ids]
    if not new_rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(_normalized_row(row) for row in new_rows)


def write_evidence_rows(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(_normalized_row(row) for row in rows)


def read_evidence_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_evidence_summary(
    path: Path,
    rows: Iterable[dict[str, str]],
    *,
    title: str = "Resumen digerido de evidencia",
) -> None:
    rows = sorted(
        list(rows),
        key=lambda item: item.get("finished_at_lima", ""),
        reverse=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_summary_markdown(rows, title=title), encoding="utf-8", newline="\n")


def _evidence_row(
    *,
    run_id: str,
    finished_at: str,
    order_id: str | None,
    status: str,
    message: str,
    duration_seconds: float | None,
    reservation_attempted: bool,
    reservation_confirmed: bool,
    details: dict[str, Any] | None,
    screenshot_path: str | None,
    screenshot_paths: list[str] | None,
) -> dict[str, str] | None:
    details = sanitize_details(details) or {}
    status_value = ResultStatus(status)
    submission_outcome = detail_text(details.get("submission_outcome"))
    defense_signal = detect_defense_signal(message, details)
    if not _is_evidence_case(
        status_value,
        details,
        submission_outcome=submission_outcome,
        defense_signal=defense_signal,
        reservation_attempted=reservation_attempted,
        reservation_confirmed=reservation_confirmed,
    ):
        return None
    timing = details.get(TIMING_DETAILS_KEY)
    timing = timing if isinstance(timing, dict) else {}
    return {
        "run_id": detail_text(run_id),
        "finished_at_lima": _format_lima_datetime(finished_at),
        "order_id": detail_text(order_id),
        "status": status_value.value,
        "detection_origin": detection_origin(details),
        "site": detail_text(details.get("sede") or details.get("site")),
        "appointment_date": detail_text(details.get("fecha") or details.get("appointment_date")),
        "appointment_hour": detail_text(details.get("hora") or details.get("appointment_hour")),
        "slots": detail_text(details.get("cupos") or details.get("slots")),
        "submission_outcome": submission_outcome,
        "confirmation_source": detail_text(details.get("confirmation_source")),
        "defense_signal": defense_signal,
        "duration_seconds": _number_text(duration_seconds),
        "total_from_available_seconds": _number_text(timing.get("total_from_available_seconds")),
        "selection_seconds": _number_text(timing.get("selection_seconds")),
        "captcha_solver_seconds": _number_text(timing.get("captcha_solver_seconds")),
        "click_to_portal_response_seconds": _number_text(
            timing.get("click_to_portal_response_seconds")
        ),
        "screenshot_path": _current_evidence_path(screenshot_path),
        "evidence_paths": _evidence_paths(details, screenshot_paths or []),
        "message": sanitize_text(message),
    }


def _is_evidence_case(
    status: ResultStatus,
    details: dict[str, Any],
    *,
    submission_outcome: str,
    defense_signal: str,
    reservation_attempted: bool,
    reservation_confirmed: bool,
) -> bool:
    if status in EVIDENCE_STATUSES:
        return True
    if reservation_attempted or reservation_confirmed:
        return True
    if submission_outcome in SUBMISSION_EVIDENCE_OUTCOMES:
        return True
    if status == ResultStatus.UNAVAILABLE and submission_outcome == "slot_lost":
        return True
    if bool(details.get("blocked_by_order_rule")):
        return True
    return bool(defense_signal)


def detect_defense_signal(message: str, details: dict[str, Any] | None = None) -> str:
    details = details or {}
    searchable = " ".join(
        [
            message,
            detail_text(details.get("error_type")),
            detail_text(details.get("portal_response")),
            detail_text(details.get("visible_text")),
        ]
    ).casefold()
    for label, patterns in DEFENSE_PATTERNS:
        if any(pattern in searchable for pattern in patterns):
            return label
    return ""


def _summary_markdown(rows: list[dict[str, str]], *, title: str) -> str:
    total = len(rows)
    by_status = Counter(row.get("status", "") for row in rows)
    by_origin = Counter(row.get("detection_origin", "") for row in rows)
    defenses = [row for row in rows if row.get("defense_signal")]
    latest = rows[:10]
    lines = [
        f"# {title}\n",
        "\n",
        "Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.\n",
        "\n",
        "## Totales\n",
        f"- Eventos indexados: {total}\n",
        f"- Reservas registradas: {by_status.get('registered', 0)}\n",
        f"- Reservas no confirmadas: {by_status.get('reservation_unconfirmed', 0)}\n",
        f"- Disponibilidades completas: {by_status.get('available', 0)}\n",
        f"- Disponibilidades parciales: {by_status.get('partial', 0)}\n",
        f"- Senales de defensa: {len(defenses)}\n",
        "\n",
        "## Origen de deteccion\n",
    ]
    origins = [(origin, count) for origin, count in sorted(by_origin.items()) if origin]
    if not origins:
        lines.append("- Sin eventos indexados todavia.\n")
    for origin, count in origins:
        if origin:
            lines.append(f"- {origin}: {count}\n")
    lines.extend(["\n", "## Ultimos eventos utiles\n"])
    if not latest:
        lines.append("- No hay eventos indexados todavia.\n")
    for row in latest:
        appointment = " ".join(
            part
            for part in (row.get("appointment_date", ""), row.get("appointment_hour", ""))
            if part
        )
        lines.append(
            "- "
            f"{row.get('finished_at_lima') or 'sin hora'} | "
            f"{row.get('order_id') or 'sin orden'} | "
            f"{row.get('status')} | "
            f"{row.get('detection_origin') or 'sin origen'} | "
            f"{appointment or 'sin cita'} | "
            f"{row.get('submission_outcome') or row.get('confirmation_source') or 'sin outcome'}\n"
        )
    lines.extend(["\n", "## Senales de defensa\n"])
    if not defenses:
        lines.append("- No se registraron senales de defensa en estos eventos.\n")
    for row in defenses[:10]:
        lines.append(
            "- "
            f"{row.get('finished_at_lima')} | {row.get('order_id')} | "
            f"{row.get('defense_signal')} | {row.get('message')}\n"
        )
    lines.extend(["\n", "## Lectura recomendada\n"])
    lines.append("- Usar `docs/evidence-index.csv` para filtrar el caso exacto.\n")
    lines.append("- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.\n")
    lines.append("- Comparar cambios contra `docs/optimization.md`.\n")
    return "".join(lines)


def _run_in_days(run: RunDetail, *, days: int, now: datetime | None) -> bool:
    parsed = parse_datetime(run.finished_at)
    if parsed is None:
        return False
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return parsed >= current - timedelta(days=max(days, 1))


def _existing_run_ids(path: Path) -> set[str]:
    return {row.get("run_id", "") for row in read_evidence_rows(path)}


def _normalized_row(row: dict[str, str]) -> dict[str, str]:
    return {field: sanitize_text(detail_text(row.get(field))) for field in CSV_FIELDS}


def _evidence_paths(details: dict[str, Any], screenshot_paths: list[str]) -> str:
    paths = [detail_text(path) for path in screenshot_paths if _current_evidence_path(path)]
    artifacts = details.get("diagnostic_artifacts")
    if isinstance(artifacts, dict):
        for values in artifacts.values():
            if isinstance(values, list):
                paths.extend(
                    detail_text(value) for value in values if _current_evidence_path(value)
                )
    for key in (
        "captcha_image_path",
        "captcha_screenshot_image_path",
        "captcha_original_html_path",
        "post_submit_html_path",
    ):
        value = detail_text(details.get(key))
        if _current_evidence_path(value):
            paths.append(value)
    return " | ".join(dict.fromkeys(path for path in paths if path))


def _current_evidence_path(value: object) -> str:
    text = detail_text(value)
    if OBSOLETE_CAPTCHA_PANEL_ARTIFACT in text:
        return ""
    return text


def _format_lima_datetime(value: str) -> str:
    return format_lima_datetime(value, default_timezone=UTC) or ""


def _number_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return ""
