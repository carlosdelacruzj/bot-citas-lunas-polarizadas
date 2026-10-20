from __future__ import annotations

import csv
import re
import tempfile
import threading
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from appointment_bot.core.models import RunDetail, RunReport
from appointment_bot.core.statuses import ResultStatus, sanitize_details
from appointment_bot.reservation_engine.timings import TIMING_DETAILS_KEY
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
EVIDENCE_MONTHLY_DIRECTORY = Path("reports/evidence/monthly")
EVIDENCE_DAILY_DIRECTORY = Path("reports/evidence/daily")
EVIDENCE_MANIFEST_PATH = Path("reports/evidence/index.md")
EVIDENCE_STATUSES = {
    ResultStatus.AVAILABLE,
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
ORDER_IDENTIFIER_PATTERN = re.compile(r"(?i)\border-[a-z0-9_*.-]+\b")
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
    "captcha_field_fill_seconds",
    "pre_click_validation_seconds",
    "submission_intent_seconds",
    "selection_stabilization_mode",
    "click_to_portal_response_seconds",
    "screenshot_path",
    "evidence_paths",
    "message",
)
_EVIDENCE_WRITE_LOCK = threading.RLock()


@dataclass(frozen=True)
class EvidenceSummaryResult:
    csv_path: Path
    markdown_path: Path
    event_count: int


def append_evidence_case(report: RunReport) -> None:
    row = evidence_row_from_report(report)
    if row is None:
        return
    with _EVIDENCE_WRITE_LOCK:
        month = _evidence_month(row)
        monthly_path = _monthly_evidence_path(month)
        append_evidence_rows(monthly_path, [row])
        monthly_rows = read_evidence_rows(monthly_path)
        _write_daily_aggregate(month, monthly_rows)
        _write_evidence_manifest({month: monthly_rows})
        if month == datetime.now(LIMA_TZ).strftime("%Y-%m"):
            _write_current_evidence_snapshot(month, monthly_rows)


def rebuild_evidence_rotation(
    rows: Iterable[dict[str, str]],
    *,
    active_month: str | None = None,
) -> None:
    with _EVIDENCE_WRITE_LOCK:
        grouped = _group_unique_evidence_rows(rows)
        manifest_rows: dict[str, list[dict[str, str]]] = {}
        for month, month_rows in sorted(grouped.items()):
            write_evidence_rows(_monthly_evidence_path(month), month_rows)
            written_rows = read_evidence_rows(_monthly_evidence_path(month))
            _write_daily_aggregate(month, written_rows)
            manifest_rows[month] = written_rows
        _write_evidence_manifest(manifest_rows)
        effective_month = active_month or (max(grouped) if grouped else None)
        if effective_month is not None:
            current_rows = read_evidence_rows(_monthly_evidence_path(effective_month))
            _write_current_evidence_snapshot(effective_month, current_rows)


def merge_evidence_rotation(
    rows: Iterable[dict[str, str]],
    *,
    active_month: str,
) -> None:
    with _EVIDENCE_WRITE_LOCK:
        grouped: dict[str, list[dict[str, str]]] = {}
        manifest_rows: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            grouped.setdefault(_evidence_month(row), []).append(row)
        for month, month_rows in sorted(grouped.items()):
            path = _monthly_evidence_path(month)
            append_evidence_rows(path, month_rows)
            written_rows = read_evidence_rows(path)
            _write_daily_aggregate(month, written_rows)
            manifest_rows[month] = written_rows
        _write_evidence_manifest(manifest_rows)
        current_rows = read_evidence_rows(_monthly_evidence_path(active_month))
        _write_current_evidence_snapshot(active_month, current_rows)


def export_evidence_summary(
    runs: Iterable[RunDetail],
    *,
    output_dir: Path,
    days: int,
    now: datetime | None = None,
    update_current: bool = False,
) -> EvidenceSummaryResult:
    effective_now = now or datetime.now(UTC)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=UTC)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        row
        for run in runs
        if _run_in_days(run, days=days, now=effective_now)
        for row in [evidence_row_from_run_detail(run)]
        if row is not None
    ]
    stamp = effective_now.astimezone(LIMA_TZ).strftime("%Y%m%d")
    csv_path = output_dir / f"evidence-events-{stamp}.csv"
    markdown_path = output_dir / f"evidence-summary-{stamp}.md"
    write_evidence_rows(csv_path, rows)
    requested_range = _requested_range(effective_now, days)
    write_evidence_summary(
        markdown_path,
        rows,
        title=f"Resumen de evidencia - ultimos {days} dias",
        generated_at=effective_now,
        requested_range=requested_range,
    )
    if update_current:
        merge_evidence_rotation(
            rows,
            active_month=effective_now.astimezone(LIMA_TZ).strftime("%Y-%m"),
        )
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
    with _EVIDENCE_WRITE_LOCK:
        useful_rows = [row for row in rows if _is_useful_evidence_row(row)]
        if not useful_rows:
            return
        existing = read_evidence_rows(path)
        existing_ids = {row.get("run_id", "") for row in existing}
        new_rows = [row for row in useful_rows if row.get("run_id") not in existing_ids]
        if new_rows:
            write_evidence_rows(path, [*existing, *new_rows])


def write_evidence_rows(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    unique: dict[str, dict[str, str]] = {}
    for row in rows:
        if _is_useful_evidence_row(row):
            unique.setdefault(str(row.get("run_id") or ""), row)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        delete=False,
    ) as file:
        temporary_path = Path(file.name)
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(_normalized_row(row) for row in unique.values())
    temporary_path.replace(path)


def read_evidence_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _evidence_month(row: dict[str, str]) -> str:
    value = str(row.get("finished_at_lima") or "").strip()
    month = value[:7]
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        return datetime.now(LIMA_TZ).strftime("%Y-%m")
    return month


def _monthly_evidence_path(month: str) -> Path:
    return EVIDENCE_MONTHLY_DIRECTORY / f"evidence-{month}.csv"


def _write_current_evidence_snapshot(
    month: str,
    rows: list[dict[str, str]],
) -> None:
    write_evidence_rows(EVIDENCE_INDEX_PATH, rows)
    write_evidence_summary(
        EVIDENCE_SUMMARY_PATH,
        rows,
        requested_range=f"mes activo {month} (America/Lima)",
    )


def _write_daily_aggregate(month: str, rows: Iterable[dict[str, str]]) -> None:
    fields = (
        "date_lima",
        "events",
        "registered",
        "available",
        "reservation_unconfirmed",
        "unknown",
        "defense_signals",
        "slot_lost",
        "captcha_invalid",
    )
    daily: dict[str, Counter[str]] = {}
    for row in rows:
        day = str(row.get("finished_at_lima") or "")[:10]
        if not day.startswith(month) or len(day) != 10:
            continue
        counts = daily.setdefault(day, Counter())
        counts["events"] += 1
        status = str(row.get("status") or "")
        if status in {"registered", "available", "reservation_unconfirmed", "unknown"}:
            counts[status] += 1
        if row.get("defense_signal"):
            counts["defense_signals"] += 1
        outcome = str(row.get("submission_outcome") or "")
        if outcome in {"slot_lost", "captcha_invalid"}:
            counts[outcome] += 1
    path = EVIDENCE_DAILY_DIRECTORY / f"evidence-daily-{month}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        delete=False,
    ) as file:
        temporary_path = Path(file.name)
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for day, counts in sorted(daily.items()):
            writer.writerow(
                {
                    field: day if field == "date_lima" else counts[field]
                    for field in fields
                }
            )
    temporary_path.replace(path)


def _write_evidence_manifest(
    updated_months: dict[str, list[dict[str, str]]] | None = None,
) -> None:
    lines = [
        "# Indice mensual de evidencia\n\n",
        f"- Generado: `{datetime.now(LIMA_TZ).isoformat(timespec='seconds')}`.\n",
        "- Los CSV mensuales son la historia compacta canonica.\n",
        "- `docs/evidence-index.csv` conserva solo el mes activo.\n",
        "- Los agregados diarios no sustituyen los eventos ni PostgreSQL.\n\n",
        "| Mes | Eventos | Rango real | CSV | Agregado diario | Artefactos |\n",
        "| --- | ---: | --- | --- | --- | --- |\n",
    ]
    monthly_lines: dict[str, str] = {}
    if EVIDENCE_MANIFEST_PATH.exists():
        for line in EVIDENCE_MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\| `(\d{4}-\d{2})` \|", line)
            if match:
                monthly_lines[match.group(1)] = f"{line}\n"
    EVIDENCE_MONTHLY_DIRECTORY.mkdir(parents=True, exist_ok=True)
    effective_updates = updated_months
    if effective_updates is None:
        effective_updates = {
            path.stem.removeprefix("evidence-"): read_evidence_rows(path)
            for path in sorted(EVIDENCE_MONTHLY_DIRECTORY.glob("evidence-????-??.csv"))
        }
    for month, rows in effective_updates.items():
        path = _monthly_evidence_path(month)
        dates = sorted(
            value
            for row in rows
            if (value := str(row.get("finished_at_lima") or "")[:10])
        )
        coverage = f"{dates[0]} a {dates[-1]}" if dates else "sin eventos"
        daily_path = EVIDENCE_DAILY_DIRECTORY / f"evidence-daily-{month}.csv"
        monthly_lines[month] = (
            f"| `{month}` | {len(rows)} | {coverage} | "
            f"[`{path.name}`](monthly/{path.name}) | "
            f"[`{daily_path.name}`](daily/{daily_path.name}) | no verificados |\n"
        )
    lines.extend(monthly_lines[month] for month in sorted(monthly_lines))
    EVIDENCE_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(EVIDENCE_MANIFEST_PATH, "".join(lines))


def write_evidence_summary(
    path: Path,
    rows: Iterable[dict[str, str]],
    *,
    title: str = "Resumen digerido de evidencia",
    generated_at: datetime | None = None,
    requested_range: str | None = None,
) -> None:
    rows = sorted(
        [row for row in rows if _is_useful_evidence_row(row)],
        key=lambda item: item.get("finished_at_lima", ""),
        reverse=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        path,
        _summary_markdown(
            rows,
            title=title,
            generated_at=generated_at or datetime.now(UTC),
            requested_range=requested_range,
        ),
    )


def _group_unique_evidence_rows(
    rows: Iterable[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        month = _evidence_month(row)
        grouped.setdefault(month, {}).setdefault(str(row.get("run_id") or ""), row)
    return {month: list(unique.values()) for month, unique in grouped.items()}


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        delete=False,
    ) as file:
        temporary_path = Path(file.name)
        file.write(content)
    temporary_path.replace(path)


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
        "order_id": _masked_order_id(order_id),
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
        "captcha_field_fill_seconds": _number_text(
            timing.get("captcha_field_fill_seconds")
        ),
        "pre_click_validation_seconds": _number_text(
            timing.get("pre_click_validation_seconds")
        ),
        "submission_intent_seconds": _number_text(
            timing.get("submission_intent_seconds")
        ),
        "selection_stabilization_mode": _selection_stabilization_mode(details),
        "click_to_portal_response_seconds": _number_text(
            timing.get("click_to_portal_response_seconds")
        ),
        "screenshot_path": _current_evidence_path(screenshot_path),
        "evidence_paths": _evidence_paths(details, screenshot_paths or []),
        "message": sanitize_text(message),
    }


def _selection_stabilization_mode(details: dict[str, Any]) -> str:
    observation = details.get("selection_observation")
    if not isinstance(observation, dict):
        return ""
    modes = observation.get("hour_stabilization_modes")
    if not isinstance(modes, list):
        return detail_text(modes)
    return "|".join(detail_text(mode) for mode in modes if detail_text(mode))


def _is_evidence_case(
    status: ResultStatus,
    details: dict[str, Any],
    *,
    submission_outcome: str,
    defense_signal: str,
    reservation_attempted: bool,
    reservation_confirmed: bool,
) -> bool:
    if status == ResultStatus.PARTIAL and _has_actionable_partial(details):
        return True
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


def _has_actionable_partial(details: dict[str, Any]) -> bool:
    if details.get("blocked_by_order_rule") or details.get("blocked_selected_for_evidence"):
        return True
    dates = [details.get("fecha"), details.get("appointment_date")]
    hours = [
        details.get("hora"),
        details.get("appointment_hour"),
        details.get("hour_options"),
    ]
    return _has_selectable_value(dates) and _has_selectable_value(hours)


def _is_useful_evidence_row(row: dict[str, str]) -> bool:
    if row.get("status") != ResultStatus.PARTIAL.value:
        return True
    if row.get("submission_outcome") or row.get("defense_signal"):
        return True
    return _has_selectable_value(row.get("appointment_date")) and _has_selectable_value(
        row.get("appointment_hour")
    )


def _has_selectable_value(value: object) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(_has_selectable_value(item) for item in value)
    text = detail_text(value).strip().casefold()
    return bool(text) and not any(
        marker in text
        for marker in ("sin cupo", "no disponible", "no hay horario", "seleccione")
    )


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


def _summary_markdown(
    rows: list[dict[str, str]],
    *,
    title: str,
    generated_at: datetime,
    requested_range: str | None,
) -> str:
    total = len(rows)
    by_status = Counter(row.get("status", "") for row in rows)
    by_origin = Counter(row.get("detection_origin", "") for row in rows)
    defenses = [row for row in rows if row.get("defense_signal")]
    latest = rows[:10]
    finished_times = sorted(
        row["finished_at_lima"] for row in rows if row.get("finished_at_lima")
    )
    lines = [
        f"# {title}\n",
        "\n",
        "Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.\n",
        "\n",
        "## Corte y cobertura\n",
        f"- Generado: `{_lima_timestamp(generated_at)}`.\n",
    ]
    if requested_range:
        lines.append(f"- Ventana solicitada: {requested_range}.\n")
    if finished_times:
        lines.append(
            "- Rango real de eventos indexados: "
            f"`{finished_times[0]}` a `{finished_times[-1]}` (America/Lima).\n"
        )
    else:
        lines.append("- Rango real de eventos indexados: sin eventos con hora de cierre.\n")
    lines.extend(
        [
            "- Cobertura temporal verificable: "
            f"{len(finished_times)}/{total} eventos con hora de cierre.\n",
            "- Fuente: filas sanitizadas del indice compacto de evidencia.\n",
            "\n",
            "## Limites\n",
            "- Es un snapshot generado; no representa el runtime ni PostgreSQL en vivo.\n",
            "- Incluye solo eventos utiles definidos por la politica de evidencia, "
            "no todos los runs.\n",
            "- Una ruta indexada no prueba que el artefacto siga retenido; "
            "verificarla antes de citarla.\n",
            "- La ausencia de un evento no demuestra que el portal no haya sido consultado.\n",
            "\n",
        ]
    )
    lines.extend(
        [
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
    )
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
    lines.append("- Comparar cambios contra `docs/contracts/optimization.md`.\n")
    return "".join(lines)


def _requested_range(now: datetime, days: int) -> str:
    start = now - timedelta(days=max(days, 1))
    return f"`{_lima_timestamp(start)}` a `{_lima_timestamp(now)}`"


def _lima_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return f"{value.astimezone(LIMA_TZ).strftime('%Y-%m-%d %H:%M:%S')} America/Lima"


def _run_in_days(run: RunDetail, *, days: int, now: datetime | None) -> bool:
    parsed = parse_datetime(run.finished_at)
    if parsed is None:
        return False
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return parsed >= current - timedelta(days=max(days, 1))


def _normalized_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {
        field: ORDER_IDENTIFIER_PATTERN.sub(
            "order-***",
            sanitize_text(detail_text(row.get(field))),
        )
        for field in CSV_FIELDS
    }
    normalized["order_id"] = _masked_order_id(row.get("order_id"))
    return normalized


def _masked_order_id(value: object) -> str:
    return "order-***" if detail_text(value) else ""


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
