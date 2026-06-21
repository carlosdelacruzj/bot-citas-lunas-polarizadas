from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult, RunReport
from appointment_bot.flows.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    AppointmentOptionsNotRefreshed,
    click_program_action,
    ensure_reservation_captcha_loaded,
    has_available_date_options,
    open_hidden_appointment_panel_for_observer,
    read_appointment_availability,
    select_available_appointment,
    select_available_site_for_observer,
)
from appointment_bot.flows.login import login
from appointment_bot.services.run_reporting import finalize_report
from appointment_bot.utils.screenshots import (
    save_result_screenshot,
    save_revealed_element_screenshot,
    save_screenshot,
)

logger = logging.getLogger(__name__)


def run_observer_with_report(
    settings: Settings,
    *,
    cancel_event: threading.Event | None = None,
    on_check: Callable[
        [AvailabilityResult, Path | None, int, int | None],
        None,
    ]
    | None = None,
) -> RunReport:
    run_id = f"observer-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    started_at_dt = datetime.now()
    started_at = started_at_dt.isoformat(timespec="seconds")
    screenshot_paths: list[Path] = []
    error_screenshot_path = None

    try:
        with open_page(settings) as page:
            try:
                login(page, settings)
                page = click_program_action(page)
                page = open_hidden_appointment_panel_for_observer(page)
                result, result_screenshot = _monitor_observer(
                    page,
                    settings,
                    cancel_event,
                    on_check,
                )
                if result_screenshot is not None:
                    screenshot_paths.insert(0, result_screenshot)

                details = dict(result.details or {})
                details["mode"] = "observer"
                result = AvailabilityResult(result.status, result.message, details)
                report = finalize_report(
                    RunReport(
                        status=result.status,
                        message=result.message,
                        exit_code=0,
                        run_id=run_id,
                        started_at=started_at,
                        details=details,
                        screenshot_path=(str(screenshot_paths[0]) if screenshot_paths else None),
                        screenshot_paths=[str(path) for path in screenshot_paths] or None,
                    ),
                    settings,
                    started_at_dt=started_at_dt,
                )
                return report
            except Exception:
                if settings.screenshot_on_error:
                    error_screenshot_path = _save_sanitized_observer_screenshot(
                        page,
                        settings,
                        "observer-error",
                    )
                raise
    except Exception as exc:
        logger.exception("Observer availability check failed")
        return finalize_report(
            RunReport(
                status="error",
                message=str(exc),
                exit_code=1,
                run_id=run_id,
                started_at=started_at,
                details={"mode": "observer"},
                screenshot_path=(str(error_screenshot_path) if error_screenshot_path else None),
            ),
            settings,
            started_at_dt=started_at_dt,
        )


def _monitor_observer(
    page,
    settings: Settings,
    cancel_event: threading.Event | None = None,
    on_check: Callable[
        [AvailabilityResult, Path | None, int, int | None],
        None,
    ]
    | None = None,
) -> tuple[AvailabilityResult, Path | None]:
    deadline = time.monotonic() + settings.monitor_window_seconds
    attempt = 1
    screenshot_path = None

    while True:
        if cancel_event is not None and cancel_event.is_set():
            return (
                AvailabilityResult(
                    status="paused",
                    message="La revision del observador fue interrumpida.",
                ),
                screenshot_path,
            )
        try:
            page = select_available_site_for_observer(
                page,
                timeout=settings.postback_timeout_seconds * 1_000,
            )
        except AppointmentOptionsNotRefreshed as exc:
            return AvailabilityResult(status="unknown", message=str(exc)), screenshot_path
        result = read_appointment_availability(
            page,
            include_person=False,
            timeout=settings.read_timeout_seconds * 1_000,
        )
        if result.status == "unknown":
            return result, screenshot_path

        if result.status == "available" or (
            result.status == "partial" and has_available_date_options(page)
        ):
            # El observador puede seleccionar fecha/hora para comprobar
            # cupos, pero esta funcion no importa captcha ni contiene accion de reserva.
            result = select_available_appointment(
                page,
                allow_hidden=True,
                include_person=False,
                timeout=settings.postback_timeout_seconds * 1_000,
            )
            if result.status == "available":
                screenshot_path = _save_available_observer_screenshot(page, settings)
                if on_check is not None:
                    on_check(result, screenshot_path, attempt, None)
                return result, screenshot_path

        if result.status not in {"unavailable", "partial"}:
            return result, screenshot_path
        if settings.monitor_window_seconds <= 0 or attempt >= settings.monitor_max_attempts:
            if on_check is not None:
                on_check(result, screenshot_path, attempt, None)
            return result, screenshot_path

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return result, screenshot_path
        wait_seconds = min(
            random.randint(
                settings.monitor_interval_min_seconds,
                settings.monitor_interval_max_seconds,
            ),
            max(1, int(remaining)),
        )
        if on_check is not None:
            on_check(result, screenshot_path, attempt, wait_seconds)
        if cancel_event is not None:
            if cancel_event.wait(wait_seconds):
                return (
                    AvailabilityResult(
                        status="paused",
                        message="La revision del observador fue interrumpida.",
                    ),
                    screenshot_path,
                )
        else:
            page.wait_for_timeout(wait_seconds * 1_000)
        if time.monotonic() >= deadline:
            return result, screenshot_path
        attempt += 1


def _save_sanitized_observer_screenshot(
    page,
    settings: Settings,
    label: str,
    *,
    selectors: list[str] | None = None,
) -> Path | None:
    if selectors:
        return save_result_screenshot(
            page,
            settings,
            label,
            selectors=selectors,
        )
    return save_screenshot(page, settings, label)


def _save_available_observer_screenshot(page, settings: Settings) -> Path | None:
    path = save_revealed_element_screenshot(
        page,
        settings,
        "observer-available",
        APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
        ready_check=lambda panel: ensure_reservation_captcha_loaded(
            panel,
            timeout=settings.read_timeout_seconds * 1_000,
        ),
    )
    if path is None:
        logger.warning("Skipping observer evidence because the panel or CAPTCHA was not ready")
    return path
