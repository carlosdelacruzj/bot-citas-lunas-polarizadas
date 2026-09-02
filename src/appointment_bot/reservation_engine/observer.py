from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings
from appointment_bot.core.models import AvailabilityResult, RunReport
from appointment_bot.reservation_engine.appointment_contracts import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    AppointmentOptionsNotRefreshed,
)
from appointment_bot.reservation_engine.appointment_reader import (
    read_appointment_availability,
)
from appointment_bot.reservation_engine.appointment_selection import (
    has_available_date_options,
    select_available_appointment,
)
from appointment_bot.reservation_engine.appointments import (
    open_hidden_appointment_panel_for_observer,
    select_available_site_for_observer,
)
from appointment_bot.reservation_engine.login import login
from appointment_bot.reservation_engine.ports import (
    AlertSink,
    CaptchaAuthority,
    ReservationEnginePorts,
)
from appointment_bot.reservation_engine.programs import click_program_action
from appointment_bot.reservation_engine.reservation_captcha_capture import (
    save_reservation_captcha_image,
)
from appointment_bot.reservation_engine.reservation_captcha_math import (
    has_reservation_math_captcha,
)
from appointment_bot.reservation_engine.reservation_captcha_refresh import (
    refresh_reservation_captcha,
)
from appointment_bot.utils.screenshots import (
    archive_unique_slot_capture,
    save_result_screenshot,
    save_revealed_centered_modal_screenshot,
    save_screenshot,
)

logger = logging.getLogger(__name__)

def run_observer_with_report(
    settings: Settings,
    *,
    cancel_event: threading.Event | None = None,
    capture_captcha_samples: bool = True,
    should_continue_captcha_sampling: Callable[[], bool] | None = None,
    on_check: Callable[
        [AvailabilityResult, Path | None, int, int | None],
        None,
    ]
    | None = None,
    ports: ReservationEnginePorts,
) -> RunReport:
    run_id = f"observer-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    started_at_dt = datetime.now(UTC)
    started_at = started_at_dt.isoformat(timespec="seconds")
    screenshot_paths: list[Path] = []
    error_screenshot_path = None

    try:
        with open_page(settings) as page:
            try:
                login(page, settings)
                page = click_program_action(page, observer_read_only=True)
                page = open_hidden_appointment_panel_for_observer(page)
                result, result_screenshot = _monitor_observer(
                    page,
                    settings,
                    cancel_event,
                    on_check,
                    run_id=run_id,
                    capture_captcha_samples=capture_captcha_samples,
                    should_continue_captcha_sampling=should_continue_captcha_sampling,
                    captcha_authority=ports.captcha,
                    alert_sink=ports.alerts,
                )
                if result_screenshot is not None:
                    screenshot_paths.insert(0, result_screenshot)

                details = dict(result.details or {})
                details["mode"] = "observer"
                result = AvailabilityResult(result.status, result.message, details)
                report = ports.runs.finalize_report(
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
                        "observer-error-panel-citas",
                    )
                raise
    except Exception as exc:
        logger.exception("Observer availability check failed")
        return ports.runs.finalize_report(
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
    *,
    run_id: str,
    capture_captcha_samples: bool,
    should_continue_captcha_sampling: Callable[[], bool] | None,
    captcha_authority: CaptchaAuthority,
    alert_sink: AlertSink,
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
                required_site=settings.observer_required_site,
                timeout=settings.postback_timeout_seconds * 1_000,
            )
        except AppointmentOptionsNotRefreshed as exc:
            return AvailabilityResult(status="unknown", message=str(exc)), screenshot_path
        result = read_appointment_availability(
            page,
            include_person=False,
            timeout=settings.read_timeout_seconds * 1_000,
        )
        if result.status == "unavailable":
            reload_result = _reload_and_recheck_observer_availability(page, settings)
            if reload_result is not None:
                result = reload_result
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
            if result.status == "available" and capture_captcha_samples:
                captcha_paths, shadow_event_ids = _collect_observer_captcha_samples(
                    page,
                    settings,
                    cancel_event,
                    run_id=run_id,
                    availability_details=dict(result.details or {}),
                    should_continue=should_continue_captcha_sampling,
                    captcha_authority=captcha_authority,
                    alert_sink=alert_sink,
                )
                if captcha_paths:
                    details = dict(result.details or {})
                    details["observer_captcha_image_paths"] = [
                        str(path) for path in captcha_paths
                    ]
                    details["observer_captcha_shadow_event_ids"] = shadow_event_ids
                    details["observer_captcha_shadow_enqueued"] = len(shadow_event_ids)
                    result = AvailabilityResult(
                        status=result.status,
                        message=result.message,
                        details=details,
                    )
                screenshot_path = _save_available_observer_screenshot(page, settings)
                if screenshot_path is not None:
                    archived_path = archive_unique_slot_capture(
                        settings,
                        result.details or {},
                        screenshot_path,
                    )
                    if archived_path is None:
                        logger.warning(
                            "Could not archive observer slot screenshot immediately"
                        )
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


def _reload_and_recheck_observer_availability(
    page,
    settings: Settings,
) -> AvailabilityResult | None:
    logger.info("No slots detected by observer; reloading before confirming unavailable result")
    try:
        page.reload(
            wait_until="domcontentloaded",
            timeout=settings.postback_timeout_seconds * 1_000,
        )
        page = click_program_action(page, observer_read_only=True)
        page = open_hidden_appointment_panel_for_observer(page)
        page = select_available_site_for_observer(
            page,
            required_site=settings.observer_required_site,
            timeout=settings.postback_timeout_seconds * 1_000,
        )
        result = read_appointment_availability(
            page,
            include_person=False,
            timeout=settings.read_timeout_seconds * 1_000,
        )
    except Exception:
        logger.exception("Observer reload probe failed; keeping the previous unavailable result")
        return None

    details = dict(result.details or {})
    details["reload_probe"] = True
    if result.status != "unavailable":
        return AvailabilityResult(
            status=result.status,
            message=(
                f"{result.message} "
                "La disponibilidad fue detectada por el observador despues de recargar la pagina."
            ),
            details=details,
        )
    return AvailabilityResult(
        status=result.status,
        message=result.message,
        details=details,
    )


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
    label = "observer-cupo-disponible"
    path = save_revealed_centered_modal_screenshot(
        page,
        settings,
        label,
        APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    )
    if path is None:
        logger.warning("Falling back to a full-page observer availability screenshot")
        return save_screenshot(page, settings, label)
    return path


def _collect_observer_captcha_samples(
    page,
    settings: Settings,
    cancel_event: threading.Event | None,
    *,
    run_id: str,
    availability_details: dict[str, object],
    should_continue: Callable[[], bool] | None,
    captcha_authority: CaptchaAuthority,
    alert_sink: AlertSink | None = None,
) -> tuple[list[Path], list[str]]:
    captcha_paths: list[Path] = []
    shadow_event_ids: list[str] = []
    if has_reservation_math_captcha(page):
        logger.info("Skipping observer model sampling for HTML math captcha")
        return captcha_paths, shadow_event_ids
    sample_limit = settings.observer_captcha_sample_limit
    for sample_number in range(1, sample_limit + 1):
        if cancel_event is not None and cancel_event.is_set():
            break
        if should_continue is not None and not should_continue():
            logger.info(
                "Stopping observer CAPTCHA sampling before sample %s because an order is active",
                sample_number,
            )
            break

        try:
            captcha_audit: dict[str, object] = {}
            save_reservation_captcha_image(
                page,
                settings,
                f"observer-captcha-sample-{sample_number}",
                captcha_audit=captcha_audit,
                alert_sink=alert_sink,
            )
            original_path = captcha_audit.get("captcha_original_html_path")
            if not original_path:
                raise RuntimeError(
                    "The observer CAPTCHA was not available as an original HTML image."
                )
            captcha_path = Path(str(original_path))
            captcha_paths.append(captcha_path)
            event_id = f"{run_id}:observer:captcha-{sample_number}"
            enqueued = captcha_authority.enqueue_prediction(
                event_id=event_id,
                image_path=str(captcha_path.resolve()),
                metadata={
                    "run_id": run_id,
                    "order_id": None,
                    "observer": 1,
                    "attempt": sample_number,
                    "captured_at_utc": datetime.now(UTC).isoformat(),
                    "source_image_kind": (
                        captcha_audit.get("captcha_sent_source") or "original_html"
                    ),
                    "detection_origin": availability_details.get("detection_origin"),
                    "portal_stage": "observer_captcha_sample",
                },
            )
            if enqueued:
                shadow_event_ids.append(event_id)
            else:
                logger.warning(
                    "Observer CAPTCHA shadow event was not enqueued: %s",
                    event_id,
                )
        except Exception as exc:
            logger.warning("Could not save observer CAPTCHA sample %s: %s", sample_number, exc)
            break

        if sample_number >= sample_limit:
            break
        if cancel_event is not None and cancel_event.is_set():
            break
        if not refresh_reservation_captcha(page, settings):
            logger.warning("Could not refresh observer CAPTCHA after sample %s", sample_number)
            break

    return captcha_paths, shadow_event_ids
