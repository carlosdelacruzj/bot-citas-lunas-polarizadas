from __future__ import annotations

import argparse
import json
import logging
import random
import threading
import time
from collections.abc import Callable
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings, load_settings
from appointment_bot.domain import AvailabilityResult, RunReport, public_report_dict
from appointment_bot.flows.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    AppointmentOptionsNotRefreshed,
    click_program_action,
    ensure_reservation_captcha_loaded,
    has_available_date_options,
    open_hidden_appointment_panel_for_observer,
    read_appointment_availability,
    read_observer_dom_state,
    select_available_appointment,
    select_available_site_for_observer,
)
from appointment_bot.flows.login import login
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.network_probe import SanitizedNetworkTrace
from appointment_bot.services.notifier import notify_error, notify_result
from appointment_bot.services.run_reporting import finalize_report
from appointment_bot.services.runtime import run_timeout, single_run_lock
from appointment_bot.utils.sanitization import sanitize_url
from appointment_bot.utils.screenshots import (
    save_result_screenshot,
    save_revealed_element_screenshot,
    save_screenshot,
)

logger = logging.getLogger(__name__)


def run_observer_with_report(
    settings_override: Settings | None = None,
    *,
    use_lock: bool = True,
    diagnostic: bool = False,
    visible: bool = False,
    notify: bool = True,
    record_history: bool = True,
    cancel_event: threading.Event | None = None,
    enforce_run_timeout: bool = True,
    on_check: Callable[
        [AvailabilityResult, Path | None, int, int | None],
        None,
    ]
    | None = None,
) -> RunReport:
    settings = settings_override or load_settings()
    setup_logging(settings)
    run_id = f"observer-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    started_at_dt = datetime.now()
    started_at = started_at_dt.isoformat(timespec="seconds")
    trace = SanitizedNetworkTrace()
    dom_states: list[dict[str, object]] = []
    screenshot_paths: list[Path] = []
    network_source = "unknown"
    error_screenshot_path = None
    diagnostic_paths: list[Path] = []

    try:
        lock_context = single_run_lock(settings) if use_lock else nullcontext()
        timeout_context = run_timeout(settings) if enforce_run_timeout else nullcontext()
        with (
            lock_context,
            timeout_context,
            open_page(
                settings,
                headless=False if visible else None,
                block_heavy_assets=False if diagnostic else None,
            ) as page,
        ):
            try:
                trace.attach(page)
                trace.mark("login")
                login(page, settings)
                trace.mark("program_action")
                page = click_program_action(page)

                before_state = _dom_state(
                    "before_hidden_postback",
                    read_observer_dom_state(page),
                )
                dom_states.append(before_state)
                if diagnostic:
                    path = _save_sanitized_observer_screenshot(
                        page,
                        settings,
                        "observer-before-hidden-postback",
                    )
                    if path is not None:
                        screenshot_paths.append(path)

                trace.mark("hidden_postback")
                page = open_hidden_appointment_panel_for_observer(page)
                after_state = _dom_state(
                    "after_hidden_postback",
                    read_observer_dom_state(page),
                )
                dom_states.append(after_state)
                if diagnostic:
                    path = _save_sanitized_observer_screenshot(
                        page,
                        settings,
                        "observer-after-hidden-postback",
                    )
                    if path is not None:
                        screenshot_paths.append(path)

                preloaded = _has_real_date_or_hour(before_state)
                result, result_screenshot = _monitor_observer(
                    page,
                    settings,
                    trace,
                    dom_states,
                    cancel_event,
                    on_check,
                )
                if result_screenshot is not None:
                    screenshot_paths.insert(0, result_screenshot)

                network_source = trace.classify(preloaded=preloaded)
                details = dict(result.details or {})
                details["mode"] = "observer"
                details["network_source"] = network_source
                result = AvailabilityResult(result.status, result.message, details)

                if diagnostic:
                    diagnostic_paths = list(
                        trace.save(
                            settings.diagnostics_dir,
                            dom_states=dom_states,
                            network_source=network_source,
                        )
                    )
                if notify:
                    notify_result(
                        result,
                        settings,
                        screenshot_paths[0] if screenshot_paths else None,
                        screenshot_paths=screenshot_paths,
                    )

                return finalize_report(
                    RunReport(
                        status=result.status,
                        message=result.message,
                        exit_code=0,
                        run_id=run_id,
                        started_at=started_at,
                        details={
                            **details,
                            "diagnostic_paths": [str(path) for path in diagnostic_paths],
                        },
                        screenshot_path=(str(screenshot_paths[0]) if screenshot_paths else None),
                        screenshot_paths=[str(path) for path in screenshot_paths] or None,
                    ),
                    settings,
                    record_history=record_history,
                    started_at_dt=started_at_dt,
                )
            except Exception:
                if settings.screenshot_on_error:
                    error_screenshot_path = _save_sanitized_observer_screenshot(
                        page,
                        settings,
                        "observer-error",
                    )
                if diagnostic:
                    diagnostic_paths = list(
                        trace.save(
                            settings.diagnostics_dir,
                            dom_states=dom_states,
                            network_source=network_source,
                        )
                    )
                raise
    except Exception as exc:
        logger.exception("Observer availability check failed")
        if diagnostic and not diagnostic_paths:
            try:
                diagnostic_paths = list(
                    trace.save(
                        settings.diagnostics_dir,
                        dom_states=dom_states,
                        network_source=network_source,
                    )
                )
            except OSError:
                logger.exception("Could not save observer network diagnostics")
        if notify:
            notify_error(exc, settings, error_screenshot_path)
        return finalize_report(
            RunReport(
                status="error",
                message=str(exc),
                exit_code=1,
                run_id=run_id,
                started_at=started_at,
                details={
                    "mode": "observer",
                    "network_source": network_source,
                    "diagnostic_paths": [str(path) for path in diagnostic_paths],
                },
                screenshot_path=(str(error_screenshot_path) if error_screenshot_path else None),
            ),
            settings,
            record_history=record_history,
            started_at_dt=started_at_dt,
        )


def _monitor_observer(
    page,
    settings: Settings,
    trace: SanitizedNetworkTrace,
    dom_states: list[dict[str, object]],
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
        trace.mark("site_selection")
        try:
            page = select_available_site_for_observer(
                page,
                timeout=settings.postback_timeout_seconds * 1_000,
            )
        except AppointmentOptionsNotRefreshed as exc:
            return AvailabilityResult(status="unknown", message=str(exc)), screenshot_path
        dom_states.append(
            _dom_state(f"after_site_selection_{attempt}", read_observer_dom_state(page))
        )
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
            dom_states.append(
                _dom_state(f"after_date_selection_{attempt}", read_observer_dom_state(page))
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


def _dom_state(label: str, state: dict[str, object]) -> dict[str, object]:
    state = dict(state)
    if state.get("url"):
        state["url"] = sanitize_url(str(state["url"]))
    return {"label": label, **state}


def _has_real_date_or_hour(state: dict[str, object]) -> bool:
    for key in ("date_options", "hour_options"):
        for option in state.get(key, []):
            text = str(option.get("text") or "").strip().lower()
            if text and text != "sin cupos" and not text.startswith("seleccione"):
                return True
    return False


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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="appointment-bot-probe-availability",
        description="Prueba segura de disponibilidad y origen de red sin reservar.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_observer_with_report(diagnostic=True, visible=True, notify=False)
    payload = public_report_dict(report)
    print(json.dumps(payload, ensure_ascii=False) if args.json else payload)
    raise SystemExit(report.exit_code)


if __name__ == "__main__":
    main()
