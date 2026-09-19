from __future__ import annotations

import random
import threading
from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from appointment_bot.browser.ownership import BrowserOwnershipLease
from appointment_bot.configuration.captcha import CaptchaSettings
from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.configuration.reservation import ReservationSettings, settings_for_order
from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.core.models import RunReport
from appointment_bot.db.browser_ownership import BrowserOwnershipConflict
from appointment_bot.db.observer_rotation import record_observer_rotation, select_observer_account
from appointment_bot.db.order_credentials import get_service_order_runtime
from appointment_bot.reservation_engine.observer import run_observer_with_report
from appointment_bot.reservation_engine.ports import ReservationEnginePorts
from appointment_bot.worker.recovery import ascii_fold, is_network_error, portal_defense_signal


def observer_defense_wait(message: str, settings: RuntimeSettings) -> int:
    normalized = ascii_fold(message).lower()
    if any(value in normalized for value in ("demasiadas solicitudes", "429", "too many requests")):
        return 900
    if "no disponible temporalmente" in normalized:
        return 180
    if portal_defense_signal(message):
        return max(180, settings.recovery_backoff_max_seconds)
    return 0


class _ObserverCancellation:
    def __init__(self, cancel: threading.Event, lease: BrowserOwnershipLease):
        self.cancel = cancel
        self.lease = lease

    def is_set(self) -> bool:
        return self.cancel.is_set() or self.lease.lost

    def wait(self, seconds: float) -> bool:
        # Login waits also stop promptly if browser ownership is lost.
        import time

        deadline = time.monotonic() + seconds
        while not self.is_set() and time.monotonic() < deadline:
            self.cancel.wait(min(0.25, max(0, deadline - time.monotonic())))
        return self.is_set()


def rotate_observer(
    *,
    runtime_settings: RuntimeSettings,
    reservation_settings: ReservationSettings,
    captcha_settings: CaptchaSettings,
    evidence_settings: EvidenceSettings,
    ports: ReservationEnginePorts,
    cancel_event: threading.Event,
    on_start: Callable[[str], None],
    on_check: Callable,
) -> tuple[RunReport | None, int]:
    account, wait = select_observer_account(runtime_settings)
    if account is None:
        return None, wait
    interval = max(
        30,
        random.randint(
            runtime_settings.observer_interval_min_seconds,
            runtime_settings.observer_interval_max_seconds,
        ),
    )
    try:
        lease = BrowserOwnershipLease.acquire(
            runtime_settings,
            account.order_id,
            owner_token=f"observer-{uuid4().hex}",
            purpose="observer",
        )
    except BrowserOwnershipConflict:
        record_observer_rotation(
            account, status="busy", interval=interval, settings=runtime_settings
        )
        return None, interval
    try:
        with lease:
            record_observer_rotation(
                account, status="started", interval=interval, settings=runtime_settings
            )
            order = get_service_order_runtime(account.order_id, settings=runtime_settings)
            if order is None:
                return None, interval
            cycle_settings = replace(
                settings_for_order(
                    reservation_settings=reservation_settings,
                    username=order.username,
                    password=order.password,
                    document_type=order.document_type,
                ),
                auto_reserve=False,
                monitor_window_seconds=0,
                monitor_max_attempts=1,
                monitor_site_toggle_enabled=False,
            )
            on_start(cycle_settings.safe_username)
            report = run_observer_with_report(
                cancel_event=_ObserverCancellation(cancel_event, lease),
                capture_captcha_samples=False,
                rotation_mode=True,
                on_check=on_check,
                ports=ports,
                runtime_settings=runtime_settings,
                reservation_settings=cycle_settings,
                captcha_settings=captcha_settings,
                evidence_settings=evidence_settings,
            )
    except Exception:
        record_observer_rotation(
            account,
            status="error",
            interval=interval,
            settings=runtime_settings,
            block_account=True,
            defense_seconds=max(180, runtime_settings.recovery_backoff_max_seconds),
        )
        raise
    # The isolated page is closed and its account released before any handoff.
    defense = observer_defense_wait(report.message, runtime_settings)
    failed = report.status in {"error", "unknown"}
    if failed and not defense:
        defense = max(180, runtime_settings.recovery_backoff_max_seconds)
    verified = report.status in {"available", "partial", "unavailable"}
    record_observer_rotation(
        account,
        status=report.status,
        interval=interval,
        settings=runtime_settings,
        block_account=failed and not is_network_error(report.message),
        defense_seconds=defense,
        verified=verified,
    )
    return replace(
        report,
        details={
            **(report.details or {}),
            "observer_rotation": True,
            "observer_account": cycle_settings.safe_username,
            "observer_global_wait_seconds": max(interval, defense),
        },
    ), max(interval, defense)
