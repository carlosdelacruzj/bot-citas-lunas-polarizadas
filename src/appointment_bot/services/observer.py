from __future__ import annotations

import argparse
import json
import logging
import random
import time
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings, load_settings
from appointment_bot.flows.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    AvailabilityResult,
    click_program_action,
    has_available_date_options,
    open_hidden_appointment_panel_for_observer,
    read_appointment_availability,
    read_observer_dom_state,
    select_available_appointment,
    select_available_site_for_observer,
)
from appointment_bot.flows.login import login
from appointment_bot.main import RunReport
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.network_probe import SanitizedNetworkTrace, sanitize_url
from appointment_bot.services.notifier import notify_error, notify_result
from appointment_bot.services.runtime import run_timeout, single_run_lock
from appointment_bot.utils.screenshots import (
    save_result_screenshot,
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
) -> RunReport:
    settings = settings_override or load_settings()
    setup_logging(settings)
    run_id = f"observer-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    started_at = datetime.now().isoformat(timespec="seconds")
    started = time.monotonic()
    trace = SanitizedNetworkTrace()
    dom_states: list[dict[str, object]] = []
    screenshot_paths: list[Path] = []
    network_source = "unknown"
    error_screenshot_path = None
    diagnostic_paths: list[Path] = []

    try:
        lock_context = single_run_lock(settings) if use_lock else nullcontext()
        with (
            lock_context,
            run_timeout(settings),
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

                duration = round(time.monotonic() - started, 3)
                return RunReport(
                    status=result.status,
                    message=result.message,
                    exit_code=0,
                    run_id=run_id,
                    started_at=started_at,
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    duration_seconds=duration,
                    details={
                        **details,
                        "diagnostic_paths": [str(path) for path in diagnostic_paths],
                    },
                    screenshot_path=str(screenshot_paths[0]) if screenshot_paths else None,
                    screenshot_paths=[str(path) for path in screenshot_paths] or None,
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
        return RunReport(
            status="error",
            message=str(exc),
            exit_code=1,
            run_id=run_id,
            started_at=started_at,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            duration_seconds=round(time.monotonic() - started, 3),
            details={
                "mode": "observer",
                "network_source": network_source,
                "diagnostic_paths": [str(path) for path in diagnostic_paths],
            },
            screenshot_path=(
                str(error_screenshot_path) if error_screenshot_path else None
            ),
        )


def _monitor_observer(
    page,
    settings: Settings,
    trace: SanitizedNetworkTrace,
    dom_states: list[dict[str, object]],
) -> tuple[AvailabilityResult, Path | None]:
    deadline = time.monotonic() + settings.monitor_window_seconds
    attempt = 1
    screenshot_path = None

    while True:
        trace.mark("site_selection")
        page = select_available_site_for_observer(page)
        dom_states.append(
            _dom_state(f"after_site_selection_{attempt}", read_observer_dom_state(page))
        )
        result = read_appointment_availability(page, include_person=False)
        if result.status == "unknown":
            raise RuntimeError(
                "El observador no pudo interpretar la disponibilidad de la pagina."
            )

        if result.status == "available" or (
            result.status == "partial" and has_available_date_options(page)
        ):
            # TEMP REVIEW: El observador puede seleccionar fecha/hora para comprobar
            # cupos, pero esta funcion no importa captcha ni contiene accion de reserva.
            result = select_available_appointment(
                page,
                allow_hidden=True,
                include_person=False,
            )
            dom_states.append(
                _dom_state(f"after_date_selection_{attempt}", read_observer_dom_state(page))
            )
            if result.status == "available":
                screenshot_path = _save_sanitized_observer_screenshot(
                    page,
                    settings,
                    "observer-available",
                    selectors=APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
                )
                return result, screenshot_path

        if result.status not in {"unavailable", "partial"}:
            return result, screenshot_path
        if settings.monitor_window_seconds <= 0 or attempt >= settings.monitor_max_attempts:
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
    page.evaluate(
        """() => {
            const sensitiveParts = [
                "dni", "documento", "nombre", "paterno", "materno",
                "apellido", "usuario", "username", "email", "mail"
            ];
            const controls = Array.from(document.querySelectorAll("input, textarea"));
            const sensitiveValues = controls.map(element => {
                const key = [
                    element.id, element.name, element.placeholder,
                    element.getAttribute("aria-label")
                ].join(" ").toLowerCase();
                const value = (element.value || "").trim();
                return sensitiveParts.some(part => key.includes(part)) && value.length > 2
                    ? value
                    : "";
            }).filter(Boolean);

            window.__observerScreenshotMask = {
                controls: controls.map(element => ({ element, value: element.value })),
                textNodes: []
            };
            controls.forEach(element => {
                if (element.type !== "hidden" && element.value) element.value = "***";
            });

            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const original = node.nodeValue || "";
                let masked = original.replace(/\\b\\d{8}\\b/g, "***");
                sensitiveValues.forEach(value => {
                    masked = masked.split(value).join("***");
                });
                if (masked !== original) {
                    window.__observerScreenshotMask.textNodes.push({ node, original });
                    node.nodeValue = masked;
                }
            }
        }"""
    )
    try:
        if selectors:
            return save_result_screenshot(
                page,
                settings,
                label,
                selectors=selectors,
            )
        return save_screenshot(page, settings, label)
    finally:
        page.evaluate(
            """() => {
                const mask = window.__observerScreenshotMask;
                if (!mask) return;
                mask.controls.forEach(item => { item.element.value = item.value; });
                mask.textNodes.forEach(item => { item.node.nodeValue = item.original; });
                delete window.__observerScreenshotMask;
            }"""
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="appointment-bot-probe-availability",
        description="Prueba segura de disponibilidad y origen de red sin reservar.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_observer_with_report(diagnostic=True, visible=True, notify=False)
    payload = asdict(report)
    print(json.dumps(payload, ensure_ascii=False) if args.json else payload)
    raise SystemExit(report.exit_code)


if __name__ == "__main__":
    main()
