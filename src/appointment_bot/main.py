import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from appointment_bot.browser.session import open_page
from appointment_bot.config import load_settings
from appointment_bot.debug.page_inspector import inspect_page
from appointment_bot.flows.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    PROCESS_STAGES_SCREENSHOT_SELECTORS,
    AppointmentWorkflowUnavailable,
    AvailabilityResult,
    appointment_stage_result,
    click_program_action,
    dismiss_reservation_confirmation,
    open_appointment_panel,
    read_appointment_availability,
    read_process_stages,
    select_available_site,
    solve_reservation_captcha_and_click_reserve,
    wait_for_reservation_confirmation,
)
from appointment_bot.flows.login import login
from appointment_bot.services.cleanup import cleanup_old_files
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
    details: dict[str, str] | None = None
    screenshot_path: str | None = None
    screenshot_paths: list[str] | None = None


def _report_from_result(
    result: AvailabilityResult,
    *,
    exit_code: int = 0,
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
        details=result.details,
        exit_code=exit_code,
        screenshot_path=str(all_screenshot_paths[0]) if all_screenshot_paths else None,
        screenshot_paths=[str(path) for path in all_screenshot_paths] or None,
    )


def _json_report(report: RunReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False)


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


def run_with_report() -> RunReport:
    settings = None
    state = None
    screenshot_path = None
    screenshot_paths = []
    try:
        settings = load_settings()
        setup_logging(settings)
        cleanup_old_files(settings)
        sleep_with_jitter(settings)
        state = load_run_state(settings)
        if should_skip_for_backoff(state):
            wait_seconds = seconds_until_next_run(state)
            logger.warning(
                "Skipping appointment check during backoff: %s seconds left", wait_seconds
            )
            return RunReport(
                status="skipped",
                message=f"Revision omitida por backoff. Faltan {wait_seconds} segundos.",
                exit_code=0,
            )

        logger.info("Starting appointment check for %s", settings.target_url)
        logger.info("Using login username %s", settings.safe_username)

        final_result = None
        with single_run_lock(settings), run_timeout(settings), open_page(settings) as page:
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
                    page = select_available_site(page)
                    _debug_snapshot(page, settings, "after-site-selection")
                    result = read_appointment_availability(page)
                    if result.status == "unknown":
                        save_unknown_result_diagnostic(page, settings)
                        screenshot_path = (
                            process_stages_screenshot_path
                            or save_result_screenshot(
                                page,
                                settings,
                                "result-unknown",
                            )
                        )
                    else:
                        screenshot_path = (
                            process_stages_screenshot_path
                            or _save_relevant_result_snapshot(page, settings, result.status)
                        )
                    if result.status == "available":
                        page = solve_reservation_captcha_and_click_reserve(page, settings)
                        wait_for_reservation_confirmation(page)
                        reservation_confirmation_screenshot_path = save_screenshot(
                            page,
                            settings,
                            "reservation-confirmation",
                        )
                        _debug_snapshot(page, settings, "after-reservation-click")
                        dismiss_reservation_confirmation(page)
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
                        result = AvailabilityResult(
                            status="registered",
                            message="Se resolvio el captcha y se hizo click en Reservar.",
                            details=result.details,
                        )
                    notify_result(
                        result,
                        settings,
                        screenshot_path,
                        screenshot_paths=screenshot_paths,
                    )
                    logger.info("Finished appointment check: %s", result.status)
                    final_result = result
            except AppointmentWorkflowUnavailable as exc:
                result = AvailabilityResult(status="completed", message=str(exc))
                notify_result(result, settings, screenshot_path)
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
        return _report_from_result(
            final_result,
            screenshot_path=screenshot_path,
            screenshot_paths=screenshot_paths,
        )
    except LockBusyError as exc:
        logger.warning("%s", exc)
        return RunReport(status="skipped", message=str(exc), exit_code=0)
    except Exception as exc:
        logger.exception("Appointment check failed")
        if settings is not None and state is not None:
            record_failure(settings, state)
        notify_error(exc, settings, screenshot_path)
        return RunReport(
            status="error",
            message=str(exc),
            exit_code=1,
            screenshot_path=str(screenshot_path) if screenshot_path is not None else None,
            screenshot_paths=[str(path) for path in screenshot_paths] or None,
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
