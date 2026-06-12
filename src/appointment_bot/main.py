import argparse
import json
import logging
import random
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings, load_settings
from appointment_bot.debug.page_inspector import inspect_page
from appointment_bot.flows.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    PROCESS_STAGES_SCREENSHOT_SELECTORS,
    AvailabilityResult,
    appointment_stage_result,
    click_program_action,
    dismiss_reservation_confirmation,
    has_available_date_options,
    open_appointment_panel,
    read_appointment_availability,
    read_process_stages,
    select_available_appointment,
    select_available_site,
    solve_reservation_captcha_and_click_reserve,
    wait_for_programmed_appointment_stage,
    wait_for_reservation_confirmation,
)
from appointment_bot.flows.login import login
from appointment_bot.services.cleanup import cleanup_old_files
from appointment_bot.services.database import RunRecord, create_run_record
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.notifier import (
    format_heartbeat_message,
    notify_error,
    notify_result,
    send_telegram_message,
)
from appointment_bot.services.runtime import (
    LockBusyError,
    load_run_state,
    record_failure,
    record_heartbeat,
    record_success,
    run_timeout,
    seconds_until_next_run,
    should_send_heartbeat,
    should_skip_for_backoff,
    single_run_lock,
    sleep_with_jitter,
)
from appointment_bot.utils.diagnostics import save_unknown_result_diagnostic
from appointment_bot.utils.screenshots import (
    save_error_screenshot,
    save_result_screenshot,
    save_screenshot,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunReport:
    status: str
    message: str
    exit_code: int
    run_id: str | None = None
    client_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    reservation_attempted: bool = False
    reservation_confirmed: bool = False
    details: dict[str, Any] | None = None
    screenshot_path: str | None = None
    screenshot_paths: list[str] | None = None


def _report_from_result(
    result: AvailabilityResult,
    *,
    exit_code: int = 0,
    run_id: str | None = None,
    client_id: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    duration_seconds: float | None = None,
    screenshot_path: Path | None = None,
    screenshot_paths: list[Path] | None = None,
) -> RunReport:
    all_screenshot_paths = _normalize_report_screenshot_paths(
        screenshot_path,
        screenshot_paths,
    )
    return RunReport(
        status=result.status,
        message=result.message,
        exit_code=exit_code,
        run_id=run_id,
        client_id=client_id,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        reservation_attempted=result.status in {"registered", "reservation_unconfirmed"},
        reservation_confirmed=result.status == "registered",
        details=result.details,
        screenshot_path=str(all_screenshot_paths[0]) if all_screenshot_paths else None,
        screenshot_paths=[str(path) for path in all_screenshot_paths] or None,
    )


def _json_report(report: RunReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False)


def settings_for_client(settings: Settings, *, username: str, password: str) -> Settings:
    return replace(settings, login_username=username, login_password=password)


def _finalize_report(
    report: RunReport,
    settings: Settings | None,
    *,
    record_history: bool,
    started_at_dt: datetime,
) -> RunReport:
    finished_at_dt = datetime.now()
    finished_at = finished_at_dt.isoformat(timespec="seconds")
    duration_seconds = round((finished_at_dt - started_at_dt).total_seconds(), 3)
    finalized = replace(
        report,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
    )
    if record_history and settings is not None and finalized.run_id is not None:
        _record_run_history(settings, finalized)
    return finalized


def _record_run_history(settings: Settings, report: RunReport) -> None:
    screenshot_paths = report.screenshot_paths or []
    if report.screenshot_path and report.screenshot_path not in screenshot_paths:
        screenshot_paths = [report.screenshot_path, *screenshot_paths]

    try:
        create_run_record(
            settings,
            RunRecord(
                run_id=report.run_id or "",
                client_id=report.client_id,
                status=report.status,
                message=report.message,
                exit_code=report.exit_code,
                started_at=report.started_at or "",
                finished_at=report.finished_at or "",
                duration_seconds=report.duration_seconds or 0,
                reservation_attempted=report.reservation_attempted,
                reservation_confirmed=report.reservation_confirmed,
                details=report.details,
                screenshot_path=report.screenshot_path,
            ),
            screenshot_paths=screenshot_paths,
        )
    except Exception as exc:
        logger.warning("Could not record run history: %s", exc)


def _normalize_report_screenshot_paths(
    screenshot_path: Path | None,
    screenshot_paths: list[Path] | None,
) -> list[Path]:
    paths = []
    if screenshot_path is not None:
        paths.append(screenshot_path)
    if screenshot_paths:
        paths.extend(screenshot_paths)

    unique_paths = []
    seen = set()
    for path in paths:
        path_key = str(path)
        if path_key in seen:
            continue
        seen.add(path_key)
        unique_paths.append(path)
    return unique_paths


def _debug_snapshot(page, settings, label: str) -> None:
    if not settings.debug_snapshots:
        return

    inspect_page(page, label=label)
    save_screenshot(page, settings, label=label)


def _save_relevant_result_snapshot(page, settings, status: str) -> Path | None:
    if status not in {"available", "partial"}:
        return None

    return save_result_screenshot(
        page,
        settings,
        label=f"result-{status}",
        selectors=APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    )


def _save_process_stages_snapshot(page, settings) -> Path | None:
    return save_result_screenshot(
        page,
        settings,
        label="process-stages",
        selectors=PROCESS_STAGES_SCREENSHOT_SELECTORS,
    )


def _complete_available_reservation(
    page,
    settings,
    result: AvailabilityResult,
    screenshot_path: Path | None,
) -> tuple[AvailabilityResult, Path | None, list[Path]]:
    page = solve_reservation_captcha_and_click_reserve(page, settings)
    confirmation_text_detected = wait_for_reservation_confirmation(page)
    reservation_confirmation_screenshot_path = save_screenshot(
        page,
        settings,
        "reservation-confirmation",
    )
    _debug_snapshot(page, settings, "after-reservation-click")
    dismiss_reservation_confirmation(page)
    programmed_stage = wait_for_programmed_appointment_stage(page, result.details)
    updated_process_stages_screenshot_path = _save_process_stages_snapshot(
        page,
        settings,
    )
    screenshot_paths = [
        path
        for path in [
            reservation_confirmation_screenshot_path,
            updated_process_stages_screenshot_path,
            screenshot_path,
        ]
        if path is not None
    ]
    if screenshot_paths:
        screenshot_path = screenshot_paths[0]

    details = dict(result.details or {})
    details["confirmacion_texto"] = (
        "detectada" if confirmation_text_detected else "no detectada"
    )
    details["confirmacion_etapa"] = (
        "Programado" if programmed_stage is not None else "no confirmada"
    )
    if programmed_stage is not None:
        details["fecha_programada"] = programmed_stage.date

    if not confirmation_text_detected or programmed_stage is None:
        return (
            AvailabilityResult(
                status="reservation_unconfirmed",
                message=(
                    "Se resolvio el captcha y se hizo click en Reservar, "
                    "pero no se confirmaron el mensaje y la etapa Programado."
                ),
                details=details,
            ),
            screenshot_path,
            screenshot_paths,
        )

    return (
        AvailabilityResult(
            status="registered",
            message="La reserva fue confirmada por mensaje y etapa Programado.",
            details=details,
        ),
        screenshot_path,
        screenshot_paths,
    )


def _monitor_appointment_availability(page, settings, process_stages_screenshot_path):
    deadline = time.monotonic() + settings.monitor_window_seconds
    attempt = 1
    screenshot_path = None
    screenshot_paths = (
        [process_stages_screenshot_path] if process_stages_screenshot_path is not None else []
    )

    while True:
        logger.info("Appointment availability check attempt %s", attempt)
        page = select_available_site(page)
        _debug_snapshot(page, settings, f"after-site-selection-{attempt}")
        result = read_appointment_availability(page)

        if result.status == "unknown":
            save_unknown_result_diagnostic(page, settings)
            result_screenshot_path = save_result_screenshot(
                page,
                settings,
                "result-unknown",
            )
            screenshot_path = result_screenshot_path or process_stages_screenshot_path
            return result, screenshot_path, screenshot_paths

        result_screenshot_path = _save_relevant_result_snapshot(
            page,
            settings,
            result.status,
        )
        screenshot_path = result_screenshot_path or process_stages_screenshot_path

        can_attempt_reservation = result.status == "available" or (
            result.status == "partial" and has_available_date_options(page)
        )
        if can_attempt_reservation:
            selected_result = select_available_appointment(page)
            if not settings.auto_reserve:
                if selected_result.status == "available":
                    return (
                        AvailabilityResult(
                            status="available",
                            message=(
                                "Se verificaron fecha y hora seleccionables. "
                                "La reserva automatica esta desactivada."
                            ),
                            details=selected_result.details,
                        ),
                        screenshot_path,
                        screenshot_paths,
                    )
                result = selected_result
            if selected_result.status == "available":
                return _complete_available_reservation(
                    page,
                    settings,
                    selected_result,
                    screenshot_path,
                )
            if settings.auto_reserve:
                result = selected_result

        # TEMP REVIEW: Una disponibilidad parcial tambien se vuelve a comprobar dentro
        # de la misma sesion; una fecha puede cargar sus horas en un intento posterior.
        if result.status not in {"unavailable", "partial"}:
            return result, screenshot_path, screenshot_paths

        # TEMP REVIEW: El modo rapido usa una sola revision; el monitor respeta ademas
        # un maximo explicito para no consultar la pagina indefinidamente.
        if (
            settings.monitor_window_seconds <= 0
            or attempt >= settings.monitor_max_attempts
        ):
            return result, screenshot_path, screenshot_paths

        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            logger.info("Monitor window finished after %s attempts", attempt)
            return result, screenshot_path, screenshot_paths

        wait_seconds = min(
            random.randint(
                settings.monitor_interval_min_seconds,
                settings.monitor_interval_max_seconds,
            ),
            max(1, int(remaining_seconds)),
        )
        logger.info(
            "No appointment availability detected; waiting %s seconds before retry",
            wait_seconds,
        )
        page.wait_for_timeout(wait_seconds * 1_000)
        if time.monotonic() >= deadline:
            logger.info("Monitor window finished after %s attempts", attempt)
            return result, screenshot_path, screenshot_paths
        attempt += 1


def run_with_report(
    settings_override: Settings | None = None,
    *,
    client_id: str | None = None,
    use_lock: bool = True,
    apply_jitter: bool = True,
    cleanup_files: bool = True,
    record_history: bool = True,
) -> RunReport:
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    started_at_dt = datetime.now()
    started_at = started_at_dt.isoformat(timespec="seconds")
    settings = None
    state = None
    screenshot_path = None
    screenshot_paths = []
    try:
        settings = settings_override or load_settings()
        setup_logging(settings)
        if cleanup_files:
            cleanup_old_files(settings)
        if apply_jitter:
            sleep_with_jitter(settings)
        state = load_run_state(settings)
        if should_skip_for_backoff(state):
            wait_seconds = seconds_until_next_run(state)
            logger.warning(
                "Skipping appointment check during backoff: %s seconds left", wait_seconds
            )
            return _finalize_report(
                RunReport(
                    status="skipped",
                    message=f"Revision omitida por backoff. Faltan {wait_seconds} segundos.",
                    exit_code=0,
                    run_id=run_id,
                    client_id=client_id,
                    started_at=started_at,
                ),
                settings,
                record_history=record_history,
                started_at_dt=started_at_dt,
            )

        logger.info("Starting appointment check for %s", settings.target_url)
        logger.info("Using login username %s", settings.safe_username)

        final_result = None
        lock_context = single_run_lock(settings) if use_lock else nullcontext()
        with lock_context, run_timeout(settings), open_page(settings) as page:
            try:
                login(page, settings)
                _debug_snapshot(page, settings, "after-login")
                page = click_program_action(page)
                _debug_snapshot(page, settings, "after-program-action")
                process_stages_screenshot_path = _save_process_stages_snapshot(page, settings)
                stages = read_process_stages(page)
                stage_result = appointment_stage_result(stages)
                if stage_result is not None:
                    screenshot_path = process_stages_screenshot_path
                    notify_result(stage_result, settings, screenshot_path)
                    logger.info("Finished appointment check: %s", stage_result.status)
                    final_result = stage_result
                else:
                    page = open_appointment_panel(page)
                    _debug_snapshot(page, settings, "after-appointment-panel")
                    result, screenshot_path, screenshot_paths = _monitor_appointment_availability(
                        page,
                        settings,
                        process_stages_screenshot_path,
                    )
                    notify_result(
                        result,
                        settings,
                        screenshot_path,
                        screenshot_paths=screenshot_paths,
                    )
                    logger.info("Finished appointment check: %s", result.status)
                    final_result = result
            except Exception:
                screenshot_path = save_error_screenshot(page, settings)
                raise

        state = record_success(settings, state)
        if should_send_heartbeat(settings, state):
            sent = send_telegram_message(
                settings,
                format_heartbeat_message(),
            )
            if sent:
                record_heartbeat(settings, state)

        if final_result is None:
            final_result = AvailabilityResult(
                status="completed",
                message="La revision termino sin devolver un resultado especifico.",
            )
        report = _report_from_result(
            final_result,
            run_id=run_id,
            client_id=client_id,
            started_at=started_at,
            screenshot_path=screenshot_path,
            screenshot_paths=screenshot_paths,
        )
        return _finalize_report(
            report,
            settings,
            record_history=record_history,
            started_at_dt=started_at_dt,
        )
    except LockBusyError as exc:
        logger.warning("%s", exc)
        return _finalize_report(
            RunReport(
                status="skipped",
                message=str(exc),
                exit_code=0,
                run_id=run_id,
                client_id=client_id,
                started_at=started_at,
            ),
            settings,
            record_history=record_history,
            started_at_dt=started_at_dt,
        )
    except Exception as exc:
        logger.exception("Appointment check failed")
        if settings is not None and state is not None:
            record_failure(settings, state)
        notify_error(exc, settings, screenshot_path)
        return _finalize_report(
            RunReport(
                status="error",
                message=str(exc),
                exit_code=1,
                run_id=run_id,
                client_id=client_id,
                started_at=started_at,
                screenshot_path=str(screenshot_path) if screenshot_path is not None else None,
                screenshot_paths=[str(path) for path in screenshot_paths] or None,
            ),
            settings,
            record_history=record_history,
            started_at_dt=started_at_dt,
        )


def run() -> int:
    return run_with_report().exit_code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON report after the run.",
    )
    args = parser.parse_args()

    report = run_with_report()
    if args.json:
        print(_json_report(report))
    raise SystemExit(report.exit_code)


if __name__ == "__main__":
    main()
