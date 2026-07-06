from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import time
import unicodedata
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult, RunReport
from appointment_bot.services.cleanup import cleanup_old_files
from appointment_bot.services.database_models import (
    ServiceOrderCandidate,
    ServiceOrderRuntime,
)
from appointment_bot.services.notifier import (
    notify_deferred_queue_summary,
    notify_immediate_availability,
    notify_result,
    send_telegram_message,
)
from appointment_bot.services.observer import run_observer_with_report
from appointment_bot.services.order_execution import (
    SERVICE_ORDER_LEASE_SECONDS,
    run_rapid_queue_with_settings,
    run_service_order,
)
from appointment_bot.services.order_runtime import (
    OrderReportOutcome,
    classify_order_report,
    order_done_status_from_report,
)
from appointment_bot.services.postgres_database import (
    acquire_worker_lease,
    claim_service_order,
    cleanup_expired_service_order_claims,
    get_worker_state,
    list_active_orders,
    list_observer_orders,
    mark_order_done,
    order_backoff_seconds,
    record_observer_window_metric,
    release_service_order_claim,
    release_worker_lease,
    renew_worker_lease,
    update_order_state,
    update_worker_state,
)
from appointment_bot.services.run_reporting import settings_for_order
from appointment_bot.utils.sanitization import sanitize_text
from appointment_bot.utils.screenshots import (
    remove_screenshot_paths,
    report_screenshot_paths,
)

logger = logging.getLogger(__name__)

WORKER_LEASE_SECONDS = 5 * 60
WORKER_LEASE_RENEW_INTERVAL_SECONDS = 60
DAILY_CUTOFF_TIME = datetime_time(hour=18)
DAILY_CUTOFF_TIMEZONE = ZoneInfo("America/Lima")
DAILY_CUTOFF_REASON = "daily_cutoff"
LEASE_UNAVAILABLE_REASON = "lease_unavailable"


class ContinuousWorker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()
        self._paused = get_worker_state(settings).paused
        self._running = False
        self._starting = False
        self._guard = threading.RLock()
        self._ready_event = threading.Event()
        self._owner_token: str | None = None
        self._worker_lease_renewed_at: float | None = None
        self._last_cleanup_date: date | None = None
        self._shutdown_reason: str | None = None
        self._unavailable_streak = 0
        self._hot_window_extended_until: datetime | None = None
        self._availability_alert_signatures: set[str] = set()
        self._rapid_queue_initial_confirmed = 0
        self._deferred_order_reports: list[RunReport] = []

    @property
    def is_running(self) -> bool:
        with self._guard:
            return self._running

    @property
    def shutdown_reason(self) -> str | None:
        with self._guard:
            return self._shutdown_reason

    def wait_until_ready(self, timeout: float) -> bool:
        return self._ready_event.wait(timeout)

    def status(self) -> dict[str, object]:
        state = asdict(get_worker_state(self.settings))
        state["worker_running"] = self.is_running
        state["worker_starting"] = self._starting
        state["continuous_worker_enabled"] = self.settings.continuous_worker_enabled
        return state

    def pause(self) -> dict[str, object]:
        with self._guard:
            self._paused = True
            self._cancel_event.set()
            self._update_state(
                phase="pausing",
                paused=True,
                next_check_at=None,
            )
        return self.status()

    def resume(self) -> dict[str, object]:
        with self._guard:
            self._paused = False
            # El evento se limpia cuando el ciclo pausado devolvio el control.
            self._update_state(
                phase="starting",
                paused=False,
                last_error=None,
                last_check_at=_now(),
                next_check_at=_now(),
            )
        return self.status()

    def prepare_restart(self) -> dict[str, object]:
        with self._guard:
            # Detiene el ciclo actual sin persistir una pausa para el proceso nuevo.
            self._paused = True
            self._cancel_event.set()
            self._update_state(
                phase="restarting",
                paused=False,
                next_check_at=None,
            )
        return self.status()

    def stop(self) -> None:
        self._stop_event.set()
        self._cancel_event.set()

    def run_forever(self) -> None:
        with self._guard:
            if self._starting or self._running:
                raise RuntimeError("Continuous worker is already running.")
            self._starting = True
            self._shutdown_reason = None

        lease_acquired = False
        try:
            self._owner_token = uuid4().hex
            if not acquire_worker_lease(
                self._owner_token,
                lease_seconds=WORKER_LEASE_SECONDS,
                settings=self.settings,
            ):
                with self._guard:
                    self._shutdown_reason = LEASE_UNAVAILABLE_REASON
                logger.warning("Another host owns the continuous worker lease.")
                return
            lease_acquired = True
            cleaned_claims = cleanup_expired_service_order_claims(self.settings)
            if cleaned_claims:
                logger.info("Released %s expired service order claim(s)", cleaned_claims)
            self._worker_lease_renewed_at = time.monotonic()
            with self._guard:
                self._starting = False
                self._running = True
            self._update_state(
                phase="paused" if self._paused else "starting",
                paused=self._paused,
                last_error=None,
                last_check_at=_now(),
                owner_token=self._owner_token,
            )
            self._ready_event.set()
            while not self._stop_event.is_set():
                self._renew_worker_lease_if_due(force=True)
                self._cleanup_once_per_day()
                if self._wait_while_paused():
                    break
                if self._daily_cutoff_reached():
                    with self._guard:
                        self._shutdown_reason = DAILY_CUTOFF_REASON
                    logger.info("Daily cutoff reached; no new appointment checks will be started")
                    break
                if self._wait_for_hot_window_if_needed():
                    continue
                try:
                    orders = list_observer_orders(self.settings)
                    if orders:
                        order = next(
                            (
                                candidate
                                for candidate in orders
                                if self._claim_order(candidate.order_id)
                            ),
                            None,
                        )
                        if order is None:
                            logger.info("All active service orders are currently leased")
                            self._interruptible_wait(5)
                            continue
                        queue_requested = False
                        try:
                            self._rapid_queue_initial_confirmed = 0
                            queue_requested = self._monitor_order(order)
                        finally:
                            self._release_order(order.order_id)
                        if queue_requested and self.settings.auto_reserve:
                            self._run_rapid_queue(
                                initial_confirmed_reservations=(
                                    self._rapid_queue_initial_confirmed
                                )
                            )
                        self._flush_deferred_order_reports()
                    else:
                        if list_active_orders(self.settings):
                            self._update_state(
                                phase="backoff",
                                current_order_id=None,
                                masked_account=None,
                                session_started_at=None,
                                next_check_at=_future(30),
                            )
                            self._interruptible_wait(30)
                        else:
                            self._monitor_observer()
                except Exception as exc:
                    logger.exception("Unexpected continuous worker cycle failure")
                    self._handle_unexpected_error(exc)
        finally:
            if lease_acquired and self._owner_token is not None:
                try:
                    update_worker_state(
                        self.settings,
                        expected_owner_token=self._owner_token,
                        phase="stopped",
                        current_order_id=None,
                        masked_account=None,
                        session_started_at=None,
                        next_check_at=None,
                    )
                except RuntimeError:
                    logger.warning("Worker state ownership changed before shutdown.")
                release_worker_lease(self._owner_token, settings=self.settings)
            with self._guard:
                self._starting = False
                self._running = False
                self._ready_event.set()

    def _monitor_order(
        self,
        order: ServiceOrderCandidate | ServiceOrderRuntime,
    ) -> bool:
        previous_state = get_worker_state(self.settings)
        order_settings = self._continuous_order_settings(order)
        if (
            previous_state.current_order_id not in {None, order.order_id}
            or previous_state.phase == "monitoring_observer"
            or (
                previous_state.masked_account is not None
                and previous_state.masked_account != order_settings.safe_username
            )
        ):
            self._reset_errors()
        backoff = order_backoff_seconds(order.order_id, settings=self.settings)
        if backoff > 0:
            logger.info(
                "Skipping observer order %s because it is in backoff for %s seconds",
                order.order_id,
                backoff,
            )
            return False

        self._set_session_state(
            "monitoring_observer_normal",
            order.order_id,
            order_settings.safe_username,
        )
        report = run_service_order(
            order_settings,
            order,
            lease_owner=self._owner_token or "",
            observer_mode=True,
            cancel_event=self._cancel_event,
            on_check=self._on_order_check,
        )
        self._defer_order_report_if_needed(report)
        self._record_check(report)
        if self._maybe_recovery_backoff(report):
            return False
        if bool((report.details or {}).get("credential_error")):
            failures = int((report.details or {}).get("credential_failure_count") or 0)
            paused = bool((report.details or {}).get("credential_paused"))
            send_telegram_message(
                self.settings,
                (
                    f"La orden {order.order_id} fue pausada despues de dos rechazos "
                    "de contrasena. Actualiza la clave y reactiva la orden."
                    if paused
                    else f"La orden {order.order_id} tuvo su primer rechazo de contrasena; "
                    "se intentara una vez mas en la siguiente rotacion."
                ),
            )
            logger.warning(
                "Credential rejection %s/2 for order %s; paused=%s",
                failures,
                order.order_id,
                paused,
            )
            self._reset_errors()
            return False
        outcome = classify_order_report(report)
        if bool((report.details or {}).get("deferred_to_higher_priority")):
            update_order_state(
                order.order_id,
                status=report.status,
                message=report.message,
                exit_code=report.exit_code,
                settings=self.settings,
            )
            self._reset_errors()
            logger.info(
                "Observer %s deferred a detected slot; starting the priority queue",
                order.order_id,
            )
            self._rapid_queue_initial_confirmed = 0
            return True
        if outcome is OrderReportOutcome.PAUSED:
            return False
        if outcome is OrderReportOutcome.BLOCKED:
            update_order_state(
                order.order_id,
                status=report.status,
                message=report.message,
                exit_code=report.exit_code,
                settings=self.settings,
            )
            self._reset_errors()
            return False
        if outcome is OrderReportOutcome.TERMINAL_STAGE:
            mark_order_done(
                order.order_id,
                status=order_done_status_from_report(report),
                settings=self.settings,
            )
            self._reset_errors()
            return False
        if outcome is OrderReportOutcome.REGISTERED:
            mark_order_done(order.order_id, settings=self.settings)
            self._increment_confirmed()
            self._rapid_queue_initial_confirmed = 1
            self._reset_errors()
            return True
        if outcome is OrderReportOutcome.RESERVATION_UNCONFIRMED:
            update_order_state(
                order.order_id,
                status=report.status,
                message=report.message,
                exit_code=report.exit_code,
                backoff_seconds=self.settings.error_backoff_seconds,
                settings=self.settings,
            )
            self._reset_errors()
            send_telegram_message(
                self.settings,
                f"La orden {order.order_id} envio una reserva pero no se pudo "
                "confirmar automaticamente como Programado. Se pausa solo esa orden "
                "temporalmente para revision; el worker continuara con las demas "
                "ordenes elegibles.",
            )
            return False
        if report.status == "available":
            update_order_state(
                order.order_id,
                status=report.status,
                message=report.message,
                exit_code=report.exit_code,
                settings=self.settings,
            )
            self._reset_errors()
            logger.info(
                "Observer %s detected availability without a confirmed reservation; "
                "the priority queue will not start",
                order.order_id,
            )
            return False
        if outcome is OrderReportOutcome.ROUTINE:
            self._reset_errors()
            update_order_state(
                order.order_id,
                status=report.status,
                message=report.message,
                exit_code=report.exit_code,
                settings=self.settings,
            )
            return False
        self._handle_order_error(order, report)
        return False

    def _defer_order_report_if_needed(self, report: RunReport) -> None:
        if report.status in {"available", "partial", "registered", "reservation_unconfirmed"}:
            self._deferred_order_reports.append(report)
            return
        remove_screenshot_paths(report_screenshot_paths(report))

    def _flush_deferred_order_reports(self) -> None:
        if not self._deferred_order_reports:
            return
        reports = self._deferred_order_reports
        self._deferred_order_reports = []
        summary = RunReport(
            status="completed",
            message="Evidencias diferidas del monitoreo.",
            exit_code=0,
        )
        notify_deferred_queue_summary(summary, self.settings, reports)

    def _claim_order(self, order_id: str) -> bool:
        if self._owner_token is None:
            raise RuntimeError("Continuous worker does not have an owner token.")
        return claim_service_order(
            order_id,
            owner_token=self._owner_token,
            lease_seconds=SERVICE_ORDER_LEASE_SECONDS,
            settings=self.settings,
        )

    def _release_order(self, order_id: str) -> None:
        if self._owner_token is None:
            return
        if not release_service_order_claim(
            order_id,
            owner_token=self._owner_token,
            settings=self.settings,
        ):
            logger.warning(
                "Service order lease was no longer owned during release: %s",
                order_id,
            )

    def _run_rapid_queue(
        self,
        *,
        initial_confirmed_reservations: int = 0,
        skip_order_ids: set[str] | None = None,
    ) -> None:
        self._update_state(
            phase="rapid_queue",
            current_order_id=None,
            masked_account=None,
            session_started_at=None,
        )
        report = run_rapid_queue_with_settings(
            self.settings,
            initial_confirmed_reservations=initial_confirmed_reservations,
            cancel_event=self._cancel_event,
            on_order_start=self._on_rapid_order_start,
            on_check=self._on_rapid_order_check,
            skip_order_ids=skip_order_ids,
        )
        confirmed = int((report.details or {}).get("confirmed_reservations", 0))
        if confirmed:
            self._increment_confirmed(confirmed)
        if report.status == "paused":
            return
        self._record_window_metric(report, source="rapid_queue")
        if report.exit_code != 0:
            self._handle_rapid_queue_error(report)

    def _monitor_observer(self) -> None:
        previous_state = get_worker_state(self.settings)
        cycle_settings = self._continuous_settings(self.settings)
        if previous_state.current_order_id is not None or (
            previous_state.masked_account is not None
            and previous_state.masked_account != cycle_settings.safe_username
        ):
            self._reset_errors()
        self._set_session_state("monitoring_observer", None, cycle_settings.safe_username)
        report = run_observer_with_report(
            cycle_settings,
            cancel_event=self._cancel_event,
            on_check=self._on_observer_check,
        )
        self._record_check(report)
        if self._maybe_recovery_backoff(report):
            return
        if report.status == "paused":
            return
        if report.status == "available":
            confirmation = self._confirm_observer_availability()
            self._record_check(confirmation)
            if self._maybe_recovery_backoff(confirmation):
                return
            if confirmation.status != "available":
                self._update_state(availability_signature=None)
                if confirmation.status in {"unavailable", "partial"}:
                    self._reset_errors()
                    return
                self._handle_observer_error(confirmation)
                return
            self._notify_confirmed_observer_availability(confirmation)
            self._reset_errors()
            return
        if report.status in {"unavailable", "partial"}:
            self._update_state(availability_signature=None)
            self._reset_errors()
            return
        self._handle_observer_error(report)

    def _confirm_observer_availability(self) -> RunReport:
        confirmation_settings = replace(
            self._continuous_settings(self.settings),
            monitor_window_seconds=0,
            monitor_max_attempts=1,
        )
        return run_observer_with_report(
            confirmation_settings,
            cancel_event=self._cancel_event,
        )

    def _notify_confirmed_observer_availability(self, report: RunReport) -> None:
        signature = _availability_signature(report)
        state = get_worker_state(self.settings)
        if signature == state.availability_signature:
            remove_screenshot_paths(report_screenshot_paths(report))
            return
        result = AvailabilityResult(
            status=report.status,
            message=report.message,
            details=report.details,
        )
        screenshot_path = Path(report.screenshot_path) if report.screenshot_path else None
        delivered = notify_result(result, self.settings, screenshot_path)
        remove_screenshot_paths(report_screenshot_paths(report))
        if delivered or not self.settings.telegram_enabled:
            self._update_state(availability_signature=signature)

    def _handle_order_error(
        self,
        order: ServiceOrderCandidate | ServiceOrderRuntime,
        report: RunReport,
    ) -> None:
        defense_signal = _portal_defense_signal(report.message)
        if defense_signal is not None:
            self._increase_errors(report.message)
            update_order_state(
                order.order_id,
                status="error",
                message=report.message,
                exit_code=1,
                backoff_seconds=self.settings.error_backoff_seconds,
                settings=self.settings,
            )
            send_telegram_message(
                self.settings,
                "El portal mostro una posible defensa durante el monitoreo "
                f"({defense_signal}) para {order.order_id}. "
                f"El worker esperara {self.settings.error_backoff_seconds} segundos.",
            )
            self._wait_retry(self.settings.error_backoff_seconds, phase="backoff")
            self._reset_errors()
            return
        failures = self._increase_errors(report.message)
        if report.status == "reservation_unconfirmed":
            self._apply_order_backoff(order, report)
            return
        if _is_network_error(report.message) and failures <= len(
            self.settings.session_retry_delays_seconds
        ):
            delay = self.settings.session_retry_delays_seconds[failures - 1]
            self._wait_retry(delay)
            return
        self._apply_order_backoff(order, report)

    def _handle_observer_error(self, report: RunReport) -> None:
        failures = self._increase_errors(report.message)
        if failures <= len(self.settings.session_retry_delays_seconds):
            self._wait_retry(self.settings.session_retry_delays_seconds[failures - 1])
            return
        send_telegram_message(
            self.settings,
            "El observador continuo acumulo fallos. "
            f"Reintentara en {self.settings.error_backoff_seconds} segundos.",
        )
        self._wait_retry(self.settings.error_backoff_seconds, phase="backoff")
        self._reset_errors()

    def _handle_rapid_queue_error(self, report: RunReport) -> None:
        failures = self._increase_errors(report.message)
        if failures <= len(self.settings.session_retry_delays_seconds):
            self._wait_retry(self.settings.session_retry_delays_seconds[failures - 1])
            return
        self._wait_retry(self.settings.error_backoff_seconds, phase="backoff")
        self._reset_errors()

    def _handle_unexpected_error(self, error: Exception) -> None:
        try:
            failures = self._increase_errors(str(error))
        except Exception:
            logger.exception("Could not persist unexpected worker failure")
            self._stop_event.wait(self.settings.error_backoff_seconds)
            return
        delays = self.settings.session_retry_delays_seconds
        if failures <= len(delays):
            self._wait_retry(delays[failures - 1])
            return
        send_telegram_message(
            self.settings,
            "El trabajador continuo encontro tres fallos internos. "
            f"Reintentara en {self.settings.error_backoff_seconds} segundos.",
        )
        self._wait_retry(self.settings.error_backoff_seconds, phase="backoff")
        self._reset_errors()

    def _apply_order_backoff(self, order: ServiceOrderRuntime, report: RunReport) -> None:
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=1,
            backoff_seconds=self.settings.error_backoff_seconds,
            settings=self.settings,
        )
        send_telegram_message(
            self.settings,
            f"La orden {order.order_id} entro en backoff por errores consecutivos. "
            "Se conserva su prioridad y no se procesaran ordenes posteriores.",
        )
        self._wait_for_backoff(order, self.settings.error_backoff_seconds)
        self._reset_errors()

    def _wait_for_backoff(self, order: ServiceOrderRuntime, seconds: int) -> None:
        self._update_state(
            phase="backoff",
            current_order_id=order.order_id,
            next_check_at=_future(seconds),
        )
        self._interruptible_wait(seconds)

    def _wait_retry(self, seconds: int, *, phase: str = "retry_wait") -> None:
        self._update_state(
            phase=phase,
            session_started_at=None,
            next_check_at=_future(seconds),
        )
        self._interruptible_wait(seconds)

    def _wait_while_paused(self) -> bool:
        while not self._stop_event.is_set():
            if self._daily_cutoff_reached():
                with self._guard:
                    self._shutdown_reason = DAILY_CUTOFF_REASON
                logger.info("Daily cutoff reached while the worker was paused")
                return True
            with self._guard:
                paused = self._paused
            if not paused:
                self._cancel_event.clear()
                return False
            self._update_state(
                phase="paused",
                paused=True,
                session_started_at=None,
                next_check_at=None,
            )
            self._renew_worker_lease_if_due()
            self._stop_event.wait(1)
        return True

    def _interruptible_wait(self, seconds: int) -> None:
        deadline = datetime.now() + timedelta(seconds=max(0, seconds))
        while datetime.now() < deadline and not self._stop_event.is_set():
            if self._daily_cutoff_reached():
                return
            self._renew_worker_lease_if_due()
            with self._guard:
                if self._paused:
                    return
            self._stop_event.wait(min(1, max(0, (deadline - datetime.now()).total_seconds())))

    def _continuous_order_settings(
        self,
        order: ServiceOrderCandidate | ServiceOrderRuntime,
    ) -> Settings:
        settings = settings_for_order(
            self.settings,
            username=order.username,
            password=getattr(order, "password", ""),
        )
        return self._continuous_settings(settings)

    def _continuous_settings(self, settings: Settings) -> Settings:
        return replace(
            settings,
            telegram_notify_unavailable=False,
            monitor_window_seconds=settings.observer_session_seconds,
            monitor_max_attempts=settings.observer_max_attempts,
            monitor_interval_min_seconds=settings.observer_interval_min_seconds,
            monitor_interval_max_seconds=settings.observer_interval_max_seconds,
        )

    def _set_session_state(
        self,
        phase: str,
        order_id: str | None,
        masked_account: str,
    ) -> None:
        self._update_state(
            phase=phase,
            paused=False,
            current_order_id=order_id,
            masked_account=masked_account,
            session_started_at=_now(),
            next_check_at=_now(),
        )

    def health(self) -> tuple[bool, str]:
        if not self.is_running:
            return False, "worker_stopped"
        state = get_worker_state(self.settings)
        if state.paused or state.phase in {
            "paused",
            "backoff",
            DAILY_CUTOFF_REASON,
            "retry_wait",
            "recovery_backoff",
            "outside_hot_window",
        }:
            return True, state.phase
        timestamps = [
            timestamp
            for timestamp in (state.last_check_at, state.session_started_at, state.updated_at)
            if timestamp
        ]
        if not timestamps:
            return False, "worker_has_no_progress_timestamp"
        try:
            latest_progress = max(datetime.fromisoformat(timestamp) for timestamp in timestamps)
            age_seconds = (datetime.now(UTC) - latest_progress).total_seconds()
        except (TypeError, ValueError):
            return False, "worker_progress_timestamp_invalid"
        stale_after = max(
            180,
            self.settings.continuous_interval_max_seconds
            + self.settings.login_timeout_seconds
            + self.settings.postback_timeout_seconds
            + self.settings.read_timeout_seconds
            + self.settings.reservation_timeout_seconds
            + 60,
        )
        if age_seconds > stale_after:
            return False, f"worker_stalled_for_{int(age_seconds)}_seconds"
        return True, "ok"

    def _update_state(self, **changes: object) -> None:
        update_worker_state(
            self.settings,
            expected_owner_token=self._owner_token,
            **changes,
        )

    def _record_check(self, report: RunReport) -> None:
        self._renew_worker_lease_if_due()
        self._record_window_metric(report, source="observer")
        self._update_state(
            last_check_at=_now(),
            next_check_at=None,
            last_error=sanitize_text(report.message) if report.exit_code else None,
        )
        if report.status == "unavailable":
            self._unavailable_streak += 1
        elif report.status in {"available", "registered", "completed", "partial"}:
            self._unavailable_streak = 0
        if report.status in {"available", "registered"}:
            self._extend_hot_window_after_availability()

    def _on_order_check(
        self,
        result: AvailabilityResult,
        attempt: int,
        next_check_seconds: int | None,
    ) -> None:
        self._renew_worker_lease_if_due()
        if result.status not in {"error", "unknown", "reservation_unconfirmed"}:
            self._reset_errors(clear_session=False)
        monitoring_mode = str((result.details or {}).get("monitoring_mode") or "normal")
        self._update_state(
            phase=f"monitoring_observer_{monitoring_mode}",
            last_check_at=_now(),
            next_check_at=(_future(next_check_seconds) if next_check_seconds is not None else None),
        )
        self._notify_immediate_availability_once(result)

    def _on_rapid_order_start(
        self,
        order: ServiceOrderCandidate | ServiceOrderRuntime,
    ) -> None:
        self._renew_worker_lease_if_due()
        order_settings = self._continuous_order_settings(order)
        self._update_state(
            phase="rapid_queue",
            current_order_id=order.order_id,
            masked_account=order_settings.safe_username,
            session_started_at=_now(),
            next_check_at=_now(),
        )

    def _on_rapid_order_check(
        self,
        result: AvailabilityResult,
        attempt: int,
        next_check_seconds: int | None,
    ) -> None:
        self._on_order_check(result, attempt, next_check_seconds)

    def _on_observer_check(
        self,
        result: AvailabilityResult,
        screenshot_path: Path | None,
        attempt: int,
        next_check_seconds: int | None,
    ) -> None:
        self._renew_worker_lease_if_due()
        if result.status not in {"error", "unknown", "reservation_unconfirmed"}:
            self._reset_errors(clear_session=False)
        self._update_state(
            last_check_at=_now(),
            next_check_at=(_future(next_check_seconds) if next_check_seconds is not None else None),
        )
        if result.status != "available":
            if result.status == "unavailable":
                self._update_state(availability_signature=None)
            return
        self._notify_immediate_availability_once(result)
        self._extend_hot_window_after_availability()

    def _notify_immediate_availability_once(self, result: AvailabilityResult) -> None:
        if result.status not in {"available", "partial"}:
            return
        signature = _availability_result_signature(result)
        if signature in self._availability_alert_signatures:
            return
        self._availability_alert_signatures.add(signature)
        self._extend_hot_window_after_availability()
        notify_immediate_availability(result, self.settings)

    def _increase_errors(self, message: str) -> int:
        message = sanitize_text(message)
        state = get_worker_state(self.settings)
        failures = state.consecutive_errors + 1
        self._update_state(
            consecutive_errors=failures,
            last_error=message,
            session_started_at=None,
        )
        return failures

    def _reset_errors(self, *, clear_session: bool = True) -> None:
        changes: dict[str, object] = {
            "consecutive_errors": 0,
            "last_error": None,
        }
        if clear_session:
            changes["session_started_at"] = None
        self._update_state(**changes)

    def _increment_confirmed(self, amount: int = 1) -> None:
        state = get_worker_state(self.settings)
        self._update_state(
            confirmed_reservations=state.confirmed_reservations + amount,
        )

    def _renew_worker_lease_if_due(self, *, force: bool = False) -> None:
        owner_token = self._owner_token
        if owner_token is None:
            raise RuntimeError("Continuous worker does not have an owner token.")
        now = time.monotonic()
        if (
            not force
            and self._worker_lease_renewed_at is not None
            and now - self._worker_lease_renewed_at < WORKER_LEASE_RENEW_INTERVAL_SECONDS
        ):
            return
        if not renew_worker_lease(
            owner_token,
            lease_seconds=WORKER_LEASE_SECONDS,
            settings=self.settings,
        ):
            raise RuntimeError("The continuous worker lease was lost.")
        self._worker_lease_renewed_at = now

    def _cleanup_once_per_day(self) -> None:
        today = date.today()
        if self._last_cleanup_date == today:
            return
        cleanup_old_files(self.settings)
        self._last_cleanup_date = today

    def _daily_cutoff_reached(self) -> bool:
        return datetime.now(DAILY_CUTOFF_TIMEZONE).time() >= DAILY_CUTOFF_TIME

    def _wait_for_hot_window_if_needed(self) -> bool:
        windows = self.settings.observer_hot_windows
        if not windows:
            return False
        now = datetime.now(DAILY_CUTOFF_TIMEZONE)
        current = now.time()
        if any(start <= current < end for start, end in windows):
            return False
        if (
            self._hot_window_extended_until is not None
            and now < self._hot_window_extended_until
        ):
            logger.info(
                "Continuing in extended hot window until %s",
                self._hot_window_extended_until.isoformat(timespec="seconds"),
            )
            return False
        self._hot_window_extended_until = None

        seconds_to_window = _seconds_until_next_window(now, windows)
        wait_seconds = min(
            random.randint(
                self.settings.outside_hot_window_min_seconds,
                self.settings.outside_hot_window_max_seconds,
            ),
            seconds_to_window,
        )
        next_check_at = _future(wait_seconds)
        logger.info(
            "Outside observer hot windows; waiting %s seconds before the next check",
            wait_seconds,
        )
        self._update_state(
            phase="outside_hot_window",
            current_order_id=None,
            masked_account=None,
            session_started_at=None,
            next_check_at=next_check_at,
        )
        self._interruptible_wait(wait_seconds)
        return True

    def _extend_hot_window_after_availability(self) -> None:
        extension_seconds = self.settings.observer_hot_window_extension_seconds
        if extension_seconds <= 0:
            return
        now = datetime.now(DAILY_CUTOFF_TIMEZONE)
        window_end = _current_window_end(now, self.settings.observer_hot_windows)
        if window_end is None:
            return
        extended_until = window_end + timedelta(seconds=extension_seconds)
        if (
            self._hot_window_extended_until is None
            or extended_until > self._hot_window_extended_until
        ):
            self._hot_window_extended_until = extended_until
            logger.info(
                "Hot window extended until %s after availability detection",
                extended_until.isoformat(timespec="seconds"),
            )

    def _maybe_recovery_backoff(self, report: RunReport) -> bool:
        defense_signal = _portal_defense_signal(report.message)
        if defense_signal is not None:
            wait_seconds = self._recovery_wait_seconds()
            send_telegram_message(
                self.settings,
                "El portal mostro una posible defensa "
                f"({defense_signal}). El worker esperara {wait_seconds} segundos.",
            )
            self._wait_retry(wait_seconds, phase="recovery_backoff")
            self._unavailable_streak = 0
            self._reset_errors()
            return True

        limit = self.settings.unavailable_streak_limit
        if limit > 0 and self._unavailable_streak >= limit:
            wait_seconds = self._recovery_wait_seconds()
            logger.warning(
                "Reached %s consecutive unavailable checks; waiting %s seconds",
                self._unavailable_streak,
                wait_seconds,
            )
            send_telegram_message(
                self.settings,
                "El worker acumulo muchas respuestas seguidas de Sin Cupos. "
                f"Se pausara {wait_seconds} segundos para bajar la huella.",
            )
            self._wait_retry(wait_seconds, phase="recovery_backoff")
            self._unavailable_streak = 0
            self._reset_errors()
            return True
        return False

    def _recovery_wait_seconds(self) -> int:
        return random.randint(
            self.settings.recovery_backoff_min_seconds,
            self.settings.recovery_backoff_max_seconds,
        )

    def _record_window_metric(self, report: RunReport, *, source: str) -> None:
        details = report.details or {}
        now = datetime.now(DAILY_CUTOFF_TIMEZONE)
        window_label = _current_window_label(now.time(), self.settings.observer_hot_windows)
        try:
            record_observer_window_metric(
                self.settings,
                metric_date=now.date(),
                window_label=window_label or "outside",
                source=source,
                report=report,
            )
        except Exception:
            logger.exception("Could not record observer window metric")
        logger.info(
            "Window metric: source=%s window=%s status=%s order=%s site=%s date=%s hour=%s",
            source,
            window_label or "outside",
            report.status,
            report.order_id,
            details.get("sede"),
            details.get("fecha"),
            details.get("hora"),
        )


def _availability_signature(report: RunReport) -> str:
    details = report.details or {}
    relevant = {
        key: details.get(key)
        for key in ("sede", "fecha", "hora", "date_options", "hour_options")
        if details.get(key) is not None
    }
    payload = json.dumps(_normalize_signature_value(relevant), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _availability_result_signature(result: AvailabilityResult) -> str:
    details = result.details or {}
    relevant = {
        key: details.get(key)
        for key in ("orden", "sede", "fecha", "hora", "date_options", "hour_options")
        if details.get(key) is not None
    }
    payload = json.dumps(_normalize_signature_value(relevant), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _portal_defense_signal(message: str) -> str | None:
    normalized = _ascii_fold(message).casefold()
    signals = (
        ("http 429", "limite HTTP 429"),
        ("http error 429", "limite HTTP 429"),
        ("response status 429", "limite HTTP 429"),
        ("status 429", "limite HTTP 429"),
        ("too many requests", "limite de solicitudes"),
        ("http 403", "bloqueo HTTP 403"),
        ("http error 403", "bloqueo HTTP 403"),
        ("response status 403", "bloqueo HTTP 403"),
        ("status 403", "bloqueo HTTP 403"),
        ("forbidden", "bloqueo HTTP 403"),
        ("access denied", "acceso denegado"),
        ("captcha inesperado", "CAPTCHA inesperado"),
        ("sesion expirada", "sesion expirada"),
        ("session expired", "sesion expirada"),
        ("inicie sesion", "sesion cerrada por el portal"),
    )
    return next((label for text, label in signals if text in normalized), None)


def _is_network_error(message: str) -> bool:
    normalized = _ascii_fold(message).casefold()
    signals = (
        "net::err_",
        "connection reset",
        "connection refused",
        "connection aborted",
        "getaddrinfo failed",
        "name resolution",
        "temporary failure in name resolution",
        "urlopen error",
        "page.goto: timeout",
    )
    return any(signal in normalized for signal in signals)


def _ascii_fold(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )


def _normalize_signature_value(value):
    if isinstance(value, dict):
        return {key: _normalize_signature_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        normalized = [_normalize_signature_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def _seconds_until_next_window(
    now: datetime,
    windows: tuple[tuple[datetime_time, datetime_time], ...],
) -> int:
    today = now.date()
    candidates = [
        datetime.combine(today, start, tzinfo=DAILY_CUTOFF_TIMEZONE)
        for start, _ in windows
        if datetime.combine(today, start, tzinfo=DAILY_CUTOFF_TIMEZONE) > now
    ]
    if not candidates:
        tomorrow = today + timedelta(days=1)
        candidates = [
            datetime.combine(tomorrow, start, tzinfo=DAILY_CUTOFF_TIMEZONE) for start, _ in windows
        ]
    return max(1, int((min(candidates) - now).total_seconds()))


def _current_window_label(
    current: datetime_time,
    windows: tuple[tuple[datetime_time, datetime_time], ...],
) -> str | None:
    for start, end in windows:
        if start <= current < end:
            return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
    return None


def _current_window_end(
    now: datetime,
    windows: tuple[tuple[datetime_time, datetime_time], ...],
) -> datetime | None:
    current = now.time()
    for start, end in windows:
        if start <= current < end:
            return datetime.combine(now.date(), end, tzinfo=DAILY_CUTOFF_TIMEZONE)
    return None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _future(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(timespec="seconds")
