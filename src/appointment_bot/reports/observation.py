from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from appointment_bot.core.models import RunDetail
from appointment_bot.reservation_engine.timings import TIMING_DETAILS_KEY
from appointment_bot.services.detail_helpers import detection_origin, parse_datetime


@dataclass(frozen=True)
class OptimizationObservationResult:
    report_path: Path
    baseline_path: Path | None
    run_count: int


def export_optimization_observation(
    runs: Iterable[RunDetail],
    *,
    start: date,
    end: date,
    output_dir: Path = Path("reports/optimization"),
    baseline_path: Path | None = None,
    promote_baseline: bool = False,
) -> OptimizationObservationResult:
    runs = list(runs)
    attempts = [run for run in runs if _is_compatible_attempt(run)]
    registered = [run for run in attempts if run.status == "registered"]
    timings = {
        key: _values(runs, key)
        for key in (
            "total_from_available_seconds",
            "selection_seconds",
            "captcha_solver_seconds",
        )
    }
    shared = _shared_slot_metrics(attempts)
    fetch = _fetch_probe_metrics(runs)
    selector_observations = [
        (run.details or {}).get("selection_observation")
        for run in runs
        if isinstance((run.details or {}).get("selection_observation"), dict)
    ]
    markdown = _markdown(
        start=start,
        end=end,
        runs=runs,
        attempts=attempts,
        registered=registered,
        timings=timings,
        shared=shared,
        fetch=fetch,
        selector_observations=selector_observations,
    )
    archive_dir = output_dir / "archive" / f"{end:%Y-%m}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    report_path = archive_dir / f"observation-{start:%Y%m%d}-{end:%Y%m%d}.md"
    report_path.write_text(markdown, encoding="utf-8", newline="\n")
    promoted_path = None
    if promote_baseline:
        effective_baseline = baseline_path or output_dir / "latest.md"
        effective_baseline.parent.mkdir(parents=True, exist_ok=True)
        relative_report = Path(
            os.path.relpath(report_path, effective_baseline.parent)
        ).as_posix()
        effective_baseline.write_text(
            "# Linea base observacional publicada\n\n"
            f"- Generada: `{datetime.now(UTC).isoformat(timespec='seconds')}`.\n"
            f"- Rango: `{start}` a `{end}` (America/Lima, inclusivo).\n"
            f"- Runs observados: {len(runs)}.\n"
            f"- Reporte: [`{report_path.name}`]({relative_report}).\n\n"
            "Es una referencia historica promovida; no representa el runtime actual.\n",
            encoding="utf-8",
            newline="\n",
        )
        promoted_path = effective_baseline
    return OptimizationObservationResult(report_path, promoted_path, len(runs))


def _shared_slot_metrics(attempts: list[RunDetail]) -> dict[str, int | float]:
    groups: dict[tuple[str, str, str], list[RunDetail]] = defaultdict(list)
    for run in attempts:
        details = run.details or {}
        key = (
            str(details.get("sede") or details.get("site") or ""),
            str(details.get("fecha") or details.get("appointment_date") or ""),
            str(details.get("hora") or details.get("appointment_hour") or ""),
        )
        if all(key):
            groups[key].append(run)
    batches = []
    for group in groups.values():
        current_batch = []
        previous_started = None
        for run in sorted(group, key=_run_started):
            started = _run_started(run)
            if previous_started is not None and (started - previous_started).total_seconds() > 300:
                if current_batch:
                    batches.append(current_batch)
                current_batch = []
            current_batch.append(run)
            previous_started = started
        if current_batch:
            batches.append(current_batch)
    shared_groups = [group for group in batches if len({run.order_id for run in group}) > 1]
    later_attempts = sum(max(len(group) - 1, 0) for group in shared_groups)
    later_registered = sum(
        sum(run.status == "registered" for run in group[1:]) for group in shared_groups
    )
    return {
        "shared_groups": len(shared_groups),
        "independent_groups": sum(len({run.order_id for run in group}) == 1 for group in batches),
        "later_attempts": later_attempts,
        "later_registered": later_registered,
        "survival_proxy": later_registered / later_attempts if later_attempts else 0.0,
    }


def _fetch_probe_metrics(runs: list[RunDetail]) -> dict[str, int]:
    fetch_runs = [run for run in runs if detection_origin(run.details or {}) == "fetch_probe"]
    with_hour = [run for run in fetch_runs if _usable_hour(run)]
    confirmed = [
        run for run in fetch_runs if run.status == "registered" or run.reservation_confirmed
    ]
    defenses = [
        run
        for run in fetch_runs
        if any(token in run.message.casefold() for token in ("403", "429", "forbidden", "denied"))
    ]
    return {
        "signals": len(fetch_runs),
        "with_visible_hour": len(with_hour),
        "confirmed": len(confirmed),
        "defenses": len(defenses),
    }


def _markdown(
    *, start, end, runs, attempts, registered, timings, shared, fetch, selector_observations
) -> str:
    conversion = len(registered) / len(attempts) if attempts else 0.0
    lines = [
        "# Linea base observacional de optimizacion\n\n",
        f"- Rango: `{start}` a `{end}` (America/Lima, inclusivo).\n",
        f"- Runs: {len(runs)}.\n",
        f"- Intentos compatibles: {len(attempts)}.\n",
        f"- `registered`: {len(registered)}.\n",
        f"- Conversion base: `{conversion:.1%}` (`registered / intentos compatibles`).\n\n",
        "No se modificaron clics, esperas, CAPTCHA, orden, concurrencia ni confirmacion.\n\n",
        "## Tiempos base\n\n",
        "| Tramo | n | p50 | p90 |\n| --- | ---: | ---: | ---: |\n",
    ]
    for key, label in (
        ("total_from_available_seconds", "Deteccion a fin"),
        ("selection_seconds", "Seleccion fecha/hora"),
        ("captcha_solver_seconds", "CAPTCHA"),
    ):
        values = timings[key]
        lines.append(
            f"| {label} | {len(values)} | {_seconds(_percentile(values, 0.5))} | "
            f"{_seconds(_percentile(values, 0.9))} |\n"
        )
    captcha = timings["captcha_solver_seconds"]
    lines.extend(["\n## CAPTCHA\n\n"])
    for threshold in (3, 5, 10, 20):
        lines.append(f"- Mayor a {threshold}s: {sum(value > threshold for value in captcha)}.\n")
    lines.extend(
        [
            "\n## Cupos compartidos y secuencia\n\n",
            f"- Tandas compartidas observadas: {shared['shared_groups']}.\n",
            f"- Grupos independientes: {shared['independent_groups']}.\n",
            f"- Intentos posteriores al primero: {shared['later_attempts']}.\n",
            f"- `registered` posteriores: {shared['later_registered']}.\n",
            f"- Proxy de supervivencia: {shared['survival_proxy']:.1%}.\n",
            "Este proxy no afirma el inventario interno del portal; mide resultados "
            "posteriores sobre la misma sede/fecha/hora.\n\n",
            "## Fetch probe\n\n",
            f"- Senales: {fetch['signals']}.\n",
            f"- Con hora util visible: {fetch['with_visible_hour']}.\n",
            f"- Confirmadas en la propia corrida: {fetch['confirmed']}.\n",
            f"- Defensas asociadas: {fetch['defenses']}.\n",
            "Permanece observacional y no autoriza reservas.\n\n",
            "## Instrumentacion desde este corte\n\n",
            f"- Runs historicos con desglose de selectores: {len(selector_observations)}.\n",
            "- Los nuevos runs guardaran lectura de opciones, postback de fecha, "
            "estabilizacion de hora y cantidades candidatas.\n",
            "- No se elimino ninguna espera; primero se acumularan muestras con DOM estable.\n\n",
            "## Decision actual\n\n",
            "- Mantener el flujo productivo sin cambios funcionales.\n",
            "- No cambiar proveedor/timeout CAPTCHA ni activar concurrencia.\n",
            "- Revisar esta linea base cuando existan nuevas muestras reales.\n",
        ]
    )
    return "".join(lines)


def _is_compatible_attempt(run: RunDetail) -> bool:
    details = run.details or {}
    submission = str(details.get("submission_outcome") or "")
    return (run.reservation_attempted or bool(submission)) and not (
        submission in {"blocked_by_order_rule", "priority_deferred"}
        or bool(details.get("blocked_by_order_rule"))
    )


def _run_started(run: RunDetail):
    return parse_datetime(run.started_at) or datetime.min.replace(tzinfo=UTC)


def _values(runs: list[RunDetail], key: str) -> list[float]:
    values = []
    for run in runs:
        timing = (run.details or {}).get(TIMING_DETAILS_KEY)
        timing = timing if isinstance(timing, dict) else {}
        try:
            if timing.get(key) not in (None, ""):
                values.append(float(timing[key]))
        except (TypeError, ValueError):
            continue
    return sorted(values)


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _usable_hour(run: RunDetail) -> bool:
    details = run.details or {}
    hour = str(details.get("hora") or details.get("appointment_hour") or "").casefold()
    return bool(hour and "sin cupos" not in hour)


def _seconds(value: float | None) -> str:
    return "sin datos" if value is None else f"{value:.3f}s"
