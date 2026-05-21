import logging

from appointment_bot.browser.session import open_page
from appointment_bot.config import load_settings
from appointment_bot.debug.page_inspector import inspect_page
from appointment_bot.flows.appointments import (
    click_program_action,
    click_reserve_appointment,
    read_appointment_availability,
    select_available_site,
)
from appointment_bot.flows.login import login
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.notifier import notify_error, notify_result
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
    try:
        settings = load_settings()
        setup_logging(settings)
        logger.info("Starting appointment check for %s", settings.target_url)
        logger.info("Using login username %s", settings.safe_username)

        with open_page(settings) as page:
            try:
                login(page, settings)
                _debug_snapshot(page, settings, "after-login")
                page = click_program_action(page)
                _debug_snapshot(page, settings, "after-program-action")
                page = click_reserve_appointment(page)
                _debug_snapshot(page, settings, "after-reserve-appointment")
                page = select_available_site(page)
                _debug_snapshot(page, settings, "after-site-selection")
                result = read_appointment_availability(page)
                if result.status == "unknown":
                    save_unknown_result_diagnostic(page, settings)
                _save_relevant_result_snapshot(page, settings, result.status)
                notify_result(result)
                logger.info("Finished appointment check: %s", result.status)
            except Exception:
                save_error_screenshot(page, settings)
                raise

        return 0
    except Exception as exc:
        logger.exception("Appointment check failed")
        notify_error(exc)
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
