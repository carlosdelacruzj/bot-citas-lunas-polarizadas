from __future__ import annotations

import csv
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from appointment_bot.core.models import RunDetail
from appointment_bot.reports.evidence import detect_defense_signal
from appointment_bot.reservation_engine.timings import TIMING_DETAILS_KEY
from appointment_bot.services.detail_helpers import parse_datetime
from appointment_bot.utils.sanitization import sanitize_text

LIMA_TZ = ZoneInfo("America/Lima")
METRIC_KEYS = {
    "total_from_available_seconds": "Deteccion a fin",
    "captcha_solver_seconds": "CAPTCHA",
    "selection_seconds": "Seleccion",
    "account_switch_seconds": "Cambio de usuario",
}


@dataclass(frozen=True)
class WeeklyReportResult:
    markdown_path: Path
    metrics_path: Path
    latest_path: Path
    run_count: int
    alerts: tuple[str, ...]


def export_weekly_report(
    runs: Iterable[RunDetail],
    *,
    start: date,
    end: date,
    output_dir: Path = Path("reports/operations"),
    latest_path: Path = Path("reports/operations/latest.md"),
) -> WeeklyReportResult:
    if end < start:
        raise ValueError("end must be greater than or equal to start.")
    all_runs = sorted(runs, key=_started_at)
    current = [run for run in all_runs if _in_range(run, start, end)]
    span = (end - start).days + 1
    previous_start = start - timedelta(days=span)
    previous_end = start - timedelta(days=1)
    previous = [run for run in all_runs if _in_range(run, previous_start, previous_end)]
    current_metrics = _metrics(current)
    previous_metrics = _metrics(previous)
    alerts = _alerts(current_metrics, previous_metrics)
    markdown = _markdown(
        current_metrics,
        previous_metrics,
        start=start,
        end=end,
        previous_start=previous_start,
        previous_end=previous_end,
        alerts=alerts,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"weekly-{start:%Y%m%d}-{end:%Y%m%d}"
    markdown_path = output_dir / f"{stem}.md"
    metrics_path = output_dir / f"{stem}.csv"
    markdown_path.write_text(markdown, encoding="utf-8", newline="\n")
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(markdown, encoding="utf-8", newline="\n")
    _write_metrics_csv(metrics_path, current_metrics, previous_metrics)
    return WeeklyReportResult(markdown_path, metrics_path, latest_path, len(current), alerts)


def _metrics(runs: list[RunDetail]) -> dict[str, Any]:
    counts = Counter()
    timing_values = {key: [] for key in METRIC_KEYS}
    attempts = 0
    previous: RunDetail | None = None
    captcha_thresholds = Counter()
    for run in runs:
        details = run.details or {}
        submission = str(details.get("submission_outcome") or "")
        programmed = run.status == "completed" and (
            str(details.get("estado") or "").casefold() == "programado"
            or "programado" in run.message.casefold()
        )
        counts["registered"] += run.status == "registered"
        counts["programmed_completed"] += programmed
        counts["completed_other"] += run.status == "completed" and not programmed
        counts["reservation_unconfirmed"] += run.status == "reservation_unconfirmed"
        counts["slot_lost"] += submission == "slot_lost"
        counts["blocked_by_order_rule"] += bool(details.get("blocked_by_order_rule")) or (
            submission == "blocked_by_order_rule"
        )
        counts["defense_signals"] += bool(detect_defense_signal(run.message, details))
        compatible_attempt = (run.reservation_attempted or bool(submission)) and not (
            submission in {"blocked_by_order_rule", "priority_deferred"}
            or bool(details.get("blocked_by_order_rule"))
        )
        if compatible_attempt:
            attempts += 1
        timing = details.get(TIMING_DETAILS_KEY)
        timing = timing if isinstance(timing, dict) else {}
        for key in METRIC_KEYS:
            if key == "account_switch_seconds":
                continue
            value = _number(timing.get(key))
            if value is not None:
                timing_values[key].append(value)
        captcha = _number(timing.get("captcha_solver_seconds"))
        if captcha is not None:
            for threshold in (3, 5, 10, 20):
                captcha_thresholds[threshold] += captcha > threshold
        if compatible_attempt:
            if (
                previous
                and previous.order_id
                and run.order_id
                and previous.order_id != run.order_id
            ):
                delta = (_started_at(run) - _finished_at(previous)).total_seconds()
                if 0 <= delta <= 300:
                    timing_values["account_switch_seconds"].append(delta)
            previous = run
    return {
        "runs": len(runs),
        "attempts": attempts,
        "counts": counts,
        "timings": {key: _percentiles(values) for key, values in timing_values.items()},
        "captcha_thresholds": captcha_thresholds,
        "slot_lost_rate": counts["slot_lost"] / attempts if attempts else 0.0,
    }


def _alerts(current: dict[str, Any], previous: dict[str, Any]) -> tuple[str, ...]:
    alerts = []
    captcha = current["captcha_thresholds"]
    if captcha[10]:
        alerts.append(f"CAPTCHA: {captcha[10]} respuestas superaron 10 segundos.")
    current_rate = current["slot_lost_rate"]
    previous_rate = previous["slot_lost_rate"]
    if (
        current["attempts"] >= 3
        and current["counts"]["slot_lost"] >= 2
        and (current_rate >= previous_rate + 0.15)
    ):
        alerts.append(
            "slot_lost: aumento sostenido "
            f"de {previous_rate:.1%} a {current_rate:.1%} sobre intentos compatibles."
        )
    return tuple(alerts)


def _markdown(current, previous, *, start, end, previous_start, previous_end, alerts) -> str:
    lines = [
        "# Reporte semanal de operacion\n\n",
        f"- Rango actual: `{start}` a `{end}` (America/Lima, inclusivo).\n",
        f"- Rango comparable anterior: `{previous_start}` a `{previous_end}`.\n",
        f"- Runs medidos: {current['runs']} actuales; {previous['runs']} anteriores.\n",
        "- Intentos medidos: "
        f"{current['attempts']} actuales; {previous['attempts']} anteriores.\n\n",
        "`registered` significa reserva confirmada por esta ejecucion. "
        "`Programado/completed` se informa aparte y nunca se suma a `registered`.\n\n",
        "## Resultados exactos\n\n",
        "| Resultado | Actual | Anterior |\n| --- | ---: | ---: |\n",
    ]
    labels = (
        ("registered", "registered"),
        ("programmed_completed", "Programado/completed"),
        ("completed_other", "completed sin Programado"),
        ("reservation_unconfirmed", "reservation_unconfirmed"),
        ("slot_lost", "slot_lost"),
        ("blocked_by_order_rule", "bloqueado por regla"),
        ("defense_signals", "senales de defensa"),
    )
    for key, label in labels:
        lines.append(f"| {label} | {current['counts'][key]} | {previous['counts'][key]} |\n")
    lines.extend(["\n## Tiempos\n\n", "| Tramo | n | p50 | p90 |\n| --- | ---: | ---: | ---: |\n"])
    for key, label in METRIC_KEYS.items():
        metric = current["timings"][key]
        lines.append(
            f"| {label} | {metric['n']} | {_seconds(metric['p50'])} | {_seconds(metric['p90'])} |\n"
        )
    lines.extend(["\n## Variabilidad CAPTCHA\n\n"])
    for threshold in (3, 5, 10, 20):
        lines.append(f"- Mas de {threshold}s: {current['captcha_thresholds'][threshold]}.\n")
    lines.extend(["\n## Alertas\n\n"])
    lines.extend(
        [f"- {sanitize_text(alert)}\n" for alert in alerts] or ["- Sin alertas para este rango.\n"]
    )
    lines.extend(
        [
            "\n## Acumulado historico\n\n",
            "El acumulado historico no se mezcla en esta tabla semanal. "
            "Consultar PostgreSQL o generar otro rango explicito cuando se necesite.\n",
        ]
    )
    return "".join(lines)


def _write_metrics_csv(path: Path, current: dict[str, Any], previous: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("metric", "current", "previous"))
        for key in (
            "registered",
            "programmed_completed",
            "reservation_unconfirmed",
            "slot_lost",
            "blocked_by_order_rule",
            "defense_signals",
        ):
            writer.writerow((key, current["counts"][key], previous["counts"][key]))
        writer.writerow(
            (
                "slot_lost_rate",
                f"{current['slot_lost_rate']:.6f}",
                f"{previous['slot_lost_rate']:.6f}",
            )
        )
        for key in METRIC_KEYS:
            for percentile in ("n", "p50", "p90"):
                writer.writerow(
                    (
                        f"{key}_{percentile}",
                        current["timings"][key][percentile],
                        previous["timings"][key][percentile],
                    )
                )


def _percentiles(values: list[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "p50": statistics.median(ordered) if ordered else None,
        "p90": _percentile(ordered, 0.9),
    }


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _number(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _in_range(run: RunDetail, start: date, end: date) -> bool:
    local = _finished_at(run).astimezone(LIMA_TZ)
    return (
        datetime.combine(start, time.min, LIMA_TZ)
        <= local
        < datetime.combine(end + timedelta(days=1), time.min, LIMA_TZ)
    )


def _started_at(run: RunDetail) -> datetime:
    return _datetime(run.started_at)


def _finished_at(run: RunDetail) -> datetime:
    return _datetime(run.finished_at)


def _datetime(value: str) -> datetime:
    parsed = parse_datetime(value) or datetime.min.replace(tzinfo=UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _seconds(value: float | None) -> str:
    return "sin datos" if value is None else f"{value:.3f}s"
