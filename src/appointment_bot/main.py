import logging

from appointment_bot.browser.session import open_page
from appointment_bot.config import load_settings
from appointment_bot.debug.page_inspector import inspect_page
from appointment_bot.flows.appointments import (
    assert_no_final_confirmation_action,
    click_program_action,
    open_appointment_panel,
    read_appointment_availability,
    select_available_site,
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


def _debug_snapshot(page, settings, label: str) -> None:
    if not settings.debug_snapshots:
        return

    inspect_page(page, label=label)
    save_screenshot(page, settings, label=label)


def _save_relevant_result_snapshot(page, settings, status: str) -> None:
    if status not in {"available", "partial"}:
        return

    save_result_screenshot(page, settings, label=f"result-{status}")


def run() -> int:
    settings = None
    state = None
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
            return 0

        logger.info("Starting appointment check for %s", settings.target_url)
        logger.info("Using login username %s", settings.safe_username)

        with single_run_lock(settings), run_timeout(settings), open_page(settings) as page:
            try:
                login(page, settings)
                _debug_snapshot(page, settings, "after-login")
                page = click_program_action(page)
                _debug_snapshot(page, settings, "after-program-action")
                page = open_appointment_panel(page)
                _debug_snapshot(page, settings, "after-appointment-panel")
                page = select_available_site(page)
                _debug_snapshot(page, settings, "after-site-selection")
                assert_no_final_confirmation_action(page)
                result = read_appointment_availability(page)
                if result.status == "unknown":
                    save_unknown_result_diagnostic(page, settings)
                _save_relevant_result_snapshot(page, settings, result.status)
                notify_result(result, settings)
                logger.info("Finished appointment check: %s", result.status)
            except Exception:
                save_error_screenshot(page, settings)
                raise

        state = record_success(settings, state)
        if should_send_heartbeat(settings, state):
            sent = send_telegram_message(
                settings,
                format_heartbeat_message(),
            )
            if sent:
                record_heartbeat(settings, state)

        return 0
    except LockBusyError as exc:
        logger.warning("%s", exc)
        return 0
    except Exception as exc:
        logger.exception("Appointment check failed")
        if settings is not None and state is not None:
            record_failure(settings, state)
        notify_error(exc, settings)
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
