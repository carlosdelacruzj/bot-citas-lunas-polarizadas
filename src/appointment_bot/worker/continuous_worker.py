from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta

from appointment_bot.config import Settings
from appointment_bot.core.models import (
    RunReport,
    ServiceOrderCandidate,
    ServiceOrderRuntime,
)
from appointment_bot.db.opportunity_bursts import reconcile_stale_opportunity_bursts
from appointment_bot.db.orders import (
    claim_service_order,
    cleanup_expired_service_order_claims,
    list_active_orders,
    list_observer_orders,
    order_backoff_seconds,
    release_service_order_claim,
)
from appointment_bot.db.runs import record_observer_window_metric
from appointment_bot.db.worker_commands import (
    claim_next_worker_command,
    complete_worker_command,
)
from appointment_bot.db.worker_state import (
    get_worker_state,
    update_worker_state,
)
from appointment_bot.reservation_engine.observer import run_observer_with_report
from appointment_bot.services.cleanup import cleanup_old_files
from appointment_bot.services.notifier import send_telegram_message
from appointment_bot.utils.sanitization import sanitize_text
from appointment_bot.worker.deferred_reports import DeferredOrderReports
from appointment_bot.worker.error_policy import WorkerErrorPolicy
from appointment_bot.worker.execution import (
    continuous_order_settings,
    continuous_settings,
    observer_confirmation_settings,
)
from appointment_bot.worker.lease import (
    LEASE_LOST_REASON,
    LEASE_UNAVAILABLE_REASON,
    WorkerLease,
)
from appointment_bot.worker.observer_results import (
    decide_observer_confirmation,
    decide_observer_report,
    notify_confirmed_observer_availability,
)
from appointment_bot.worker.opportunity_burst import OpportunityBurstCoordinator
from appointment_bot.worker.order_execution import (
    SERVICE_ORDER_LEASE_SECONDS,
    run_service_order,
)
from appointment_bot.worker.order_results import handle_observer_order_report
from appointment_bot.worker.post_reservation_review import (
    review_confirmed_orders_after_queue,
)
from appointment_bot.worker.queue_traversal import run_rapid_queue_with_settings
from appointment_bot.worker.recovery import (
    portal_defense_signal,
    recovery_wait_seconds,
)
from appointment_bot.worker.reservation_engine_ports import build_reservation_engine_ports
from appointment_bot.worker.state_callbacks import WorkerStateCallbacks
from appointment_bot.worker.windows_runtime import (
    DAILY_CUTOFF_REASON,
    WORKER_TIMEZONE,
    current_window_label,
    daily_cutoff_reached,
    extended_hot_window_until,
    hot_window_wait_decision,
)

logger = logging.getLogger(__name__)


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
        self._worker_lease = WorkerLease(settings, on_lost=self._on_worker_lease_lost)
        self._last_cleanup_date: date | None = None
        self._shutdown_reason: str | None = None
        self._hot_window_extended_until: datetime | None = None
        self._rapid_queue_initial_confirmed = 0
        self._rapid_queue_initial_confirmed_order_ids: set[str] = set()
        self._rapid_queue_follow_up_order_ids: set[str] = set()
        self._compatible_handoff_order_ids: tuple[str, ...] = ()
        self._opportunity_burst_started = False
        self._opportunity_burst_recovery_report: RunReport | None = None
        self._deferred_order_reports = DeferredOrderReports(settings)
        self._reservation_engine_ports = build_reservation_engine_ports()
        self._state_callbacks = WorkerStateCallbacks(
            settings,
            update_state=self._update_state,
            reset_errors=self._reset_errors,
            extend_hot_window_after_availability=self._extend_hot_window_after_availability,
            record_window_metric=lambda report: self._record_window_metric(
                report,
                source="observer",
            ),
        )
        self._error_policy = WorkerErrorPolicy(
            settings,
            increase_errors=self._increase_errors,
            reset_errors=self._reset_errors,
            wait_retry=self._wait_retry,
            wait_retry_phase=lambda seconds, phase: self._wait_retry(seconds, phase=phase),
            wait_for_backoff=self._wait_for_backoff,
            stop_event=self._stop_event,
        )

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
            self._prepare_restart_state()
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

        try:
            if not self._start_worker_loop():
                return
            while not self._stop_event.is_set():
                if self._run_worker_cycle_once():
                    break
        finally:
            self._stop_worker_loop()
            with self._guard:
                self._starting = False
                self._running = False
                self._ready_event.set()

    def _start_worker_loop(self) -> bool:
        if not self._worker_lease.acquire():
            with self._guard:
                self._shutdown_reason = LEASE_UNAVAILABLE_REASON
            logger.warning("Another host owns the continuous worker lease.")
            return False
        cleaned_claims = cleanup_expired_service_order_claims(self.settings)
        if cleaned_claims:
            logger.info("Released %s expired service order claim(s)", cleaned_claims)
        reconciled_bursts = reconcile_stale_opportunity_bursts(
            datetime.now(UTC),
            settings=self.settings,
        )
        if reconciled_bursts:
            logger.warning(
                "Reconciled %s unfinished opportunity burst(s) from a previous worker",
                len(reconciled_bursts),
            )
        with self._guard:
            self._starting = False
            self._running = True
        self._update_state(
            phase="paused" if self._paused else "starting",
            paused=self._paused,
            last_error=None,
            last_check_at=_now(),
            owner_token=self._worker_lease.owner_token,
        )
        self._ready_event.set()
        return True

    def _run_worker_cycle_once(self) -> bool:
        self._worker_lease.ensure_owned()
        if self._process_pending_worker_command():
            return True
        self._cleanup_once_per_day()
        if self._wait_while_paused():
            return True
        if self._daily_cutoff_reached():
            with self._guard:
                self._shutdown_reason = DAILY_CUTOFF_REASON
            logger.info("Daily cutoff reached; no new appointment checks will be started")
            return True
        if self._wait_for_hot_window_if_needed():
            return False
        try:
            self._run_available_work()
        except Exception as exc:
            logger.exception("Unexpected continuous worker cycle failure")
            self._handle_unexpected_error(exc)
        return False

    def _run_available_work(self) -> None:
        orders = list_observer_orders(self.settings)
        if orders:
            self._run_observer_order_block(orders)
            return
        if list_active_orders(self.settings, include_constrained=False):
            self._wait_for_order_backoff_gap()
            return
        self._monitor_observer()

    def _run_observer_order_block(self, orders: list[ServiceOrderCandidate]) -> None:
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
            return
        queue_requested = False
        try:
            self._rapid_queue_initial_confirmed = 0
            self._rapid_queue_initial_confirmed_order_ids = set()
            self._rapid_queue_follow_up_order_ids = set()
            self._compatible_handoff_order_ids = ()
            self._opportunity_burst_started = False
            self._opportunity_burst_recovery_report = None
            queue_requested = self._monitor_order(
                order,
                preferred_burst_order_ids=tuple(
                    candidate.order_id
                    for candidate in orders
                    if candidate.order_id != order.order_id
                ),
            )
        finally:
            self._release_order(order.order_id)
        if self._opportunity_burst_recovery_report is not None:
            if self._maybe_recovery_backoff(self._opportunity_burst_recovery_report):
                self._flush_deferred_order_reports()
                return
        if self._opportunity_burst_started:
            logger.info("Sequential opportunity handoff skipped after guarded burst")
            if self._rapid_queue_follow_up_order_ids and self.settings.auto_reserve:
                self._run_rapid_queue(
                    target_order_ids=tuple(self._rapid_queue_follow_up_order_ids),
                    inter_order_delay_enabled=False,
                )
        elif self._compatible_handoff_order_ids and self.settings.auto_reserve:
            self._run_rapid_queue(
                target_order_ids=self._compatible_handoff_order_ids,
                initial_confirmed_reservations=self._rapid_queue_initial_confirmed,
                initial_confirmed_order_ids=self._rapid_queue_initial_confirmed_order_ids,
                follow_up_order_ids=self._rapid_queue_follow_up_order_ids,
                inter_order_delay_enabled=False,
            )
        elif queue_requested and self.settings.auto_reserve:
            self._run_rapid_queue(
                initial_confirmed_reservations=self._rapid_queue_initial_confirmed,
                initial_confirmed_order_ids=self._rapid_queue_initial_confirmed_order_ids,
                follow_up_order_ids=self._rapid_queue_follow_up_order_ids,
            )
        self._flush_deferred_order_reports()

    def _wait_for_order_backoff_gap(self) -> None:
        self._update_state(
            phase="backoff",
            current_order_id=None,
            masked_account=None,
            session_started_at=None,
            next_check_at=_future(30),
        )
        self._interruptible_wait(30)

    def _stop_worker_loop(self) -> None:
        owner_token = self._worker_lease.owner_token
        if owner_token is not None:
            try:
                if not self._worker_lease.lost:
                    update_worker_state(
                        self.settings,
                        expected_owner_token=owner_token,
                        phase="stopped",
                        current_order_id=None,
                        masked_account=None,
                        session_started_at=None,
                        next_check_at=None,
                    )
            except RuntimeError:
                logger.warning("Worker state ownership changed before shutdown.")
            except Exception:
                logger.exception("Could not persist the final worker state")
            finally:
                self._worker_lease.release()

    def _monitor_order(
        self,
        order: ServiceOrderCandidate | ServiceOrderRuntime,
        *,
        preferred_burst_order_ids: tuple[str, ...] = (),
    ) -> bool:
        previous_state = get_worker_state(self.settings)
        order_settings = continuous_order_settings(self.settings, order)
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
        burst = OpportunityBurstCoordinator(
            self.settings,
            order,
            cancel_event=self._cancel_event,
            preferred_order_ids=preferred_burst_order_ids,
        )

        def on_order_check(result, attempt, next_check_seconds) -> None:
            self._state_callbacks.on_order_check(result, attempt, next_check_seconds)
            try:
                if burst.maybe_start(result):
                    self._update_state(
                        phase="opportunity_burst",
                        current_order_id=order.order_id,
                        next_check_at=None,
                    )
            except Exception:
                logger.exception(
                    "Could not start opportunity burst for detector %s; "
                    "the detector will continue normally",
                    order.order_id,
                )

        report = run_service_order(
            order_settings,
            order,
            lease_owner=self._worker_lease.required_owner_token(),
            observer_mode=True,
            cancel_event=self._cancel_event,
            on_check=on_order_check,
            opportunity_context=burst.detector_context,
        )
        burst_result = burst.finish_detector(
            report,
            on_wait=self._worker_lease.ensure_owned,
        )
        self._opportunity_burst_started = burst_result.started
        for execution in burst_result.executions:
            self._defer_order_report_if_needed(execution.report)
            self._record_window_metric(
                execution.report,
                source="opportunity_burst_order",
            )
        if burst_result.started:
            burst_summary = burst_result.summary_report()
            self._record_window_metric(burst_summary, source="opportunity_burst")
            if burst_result.completion_reason.startswith("portal_defense:"):
                self._opportunity_burst_recovery_report = burst_summary
        self._defer_order_report_if_needed(report)
        self._record_check(report)
        if self._maybe_recovery_backoff(report):
            return False
        decision = handle_observer_order_report(self.settings, order, report)
        if decision.reset_errors:
            self._reset_errors()
        if decision.confirmed_reservations:
            self._increment_confirmed(decision.confirmed_reservations)
        if burst_result.confirmed_order_ids:
            self._increment_confirmed(len(burst_result.confirmed_order_ids))
        self._rapid_queue_initial_confirmed = decision.rapid_queue_initial_confirmed
        self._rapid_queue_initial_confirmed_order_ids = set(decision.confirmed_order_ids)
        self._rapid_queue_follow_up_order_ids = set(decision.follow_up_order_ids)
        self._compatible_handoff_order_ids = (
            () if burst_result.started else decision.compatible_handoff_order_ids
        )
        confirmed_order_ids = tuple(
            dict.fromkeys(
                (*decision.confirmed_order_ids, *burst_result.confirmed_order_ids)
            )
        )
        if burst_result.started and confirmed_order_ids:
            self._update_state(
                phase="post_reservation_review",
                current_order_id=None,
                masked_account=None,
                session_started_at=None,
            )
            review_results = review_confirmed_orders_after_queue(
                self.settings,
                list(confirmed_order_ids),
                cancel_event=self._cancel_event,
            )
            self._deferred_order_reports.replace_reviewed_evidence(review_results)
        if decision.requires_error_handling:
            self._handle_order_error(order, report)
            return False
        return decision.queue_requested

    def _defer_order_report_if_needed(self, report: RunReport) -> None:
        self._deferred_order_reports.defer_if_needed(report)

    def _flush_deferred_order_reports(self) -> None:
        self._deferred_order_reports.flush()

    def _claim_order(self, order_id: str) -> bool:
        return claim_service_order(
            order_id,
            owner_token=self._worker_lease.required_owner_token(),
            lease_seconds=SERVICE_ORDER_LEASE_SECONDS,
            settings=self.settings,
        )

    def _release_order(self, order_id: str) -> None:
        owner_token = self._worker_lease.owner_token
        if owner_token is None:
            return
        if not release_service_order_claim(
            order_id,
            owner_token=owner_token,
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
        initial_confirmed_order_ids: set[str] | None = None,
        skip_order_ids: set[str] | None = None,
        follow_up_order_ids: set[str] | None = None,
        target_order_ids: tuple[str, ...] | None = None,
        inter_order_delay_enabled: bool = True,
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
            initial_confirmed_order_ids=initial_confirmed_order_ids,
            cancel_event=self._cancel_event,
            on_order_start=self._state_callbacks.on_rapid_order_start,
            on_check=self._state_callbacks.on_rapid_order_check,
            on_post_review_start=lambda: self._update_state(
                phase="post_reservation_review",
                current_order_id=None,
                masked_account=None,
                session_started_at=None,
            ),
            skip_order_ids=skip_order_ids,
            follow_up_order_ids=follow_up_order_ids,
            target_order_ids=target_order_ids,
            inter_order_delay_enabled=inter_order_delay_enabled,
        )
        confirmed = int((report.details or {}).get("confirmed_reservations", 0))
        review_results = (report.details or {}).get("post_reservation_reviews")
        if isinstance(review_results, list):
            self._deferred_order_reports.replace_reviewed_evidence(review_results)
        if confirmed:
            self._increment_confirmed(confirmed)
        if report.status == "paused":
            return
        self._record_window_metric(report, source="rapid_queue")
        if report.exit_code != 0:
            self._handle_rapid_queue_error(report)

    def _monitor_observer(self) -> None:
        previous_state = get_worker_state(self.settings)
        cycle_settings = continuous_settings(self.settings)
        if previous_state.current_order_id is not None or (
            previous_state.masked_account is not None
            and previous_state.masked_account != cycle_settings.safe_username
        ):
            self._reset_errors()
        self._set_session_state("monitoring_observer", None, cycle_settings.safe_username)
        report = run_observer_with_report(
            cycle_settings,
            cancel_event=self._cancel_event,
            should_continue_captcha_sampling=self._observer_captcha_sampling_allowed,
            on_check=self._state_callbacks.on_observer_check,
            ports=self._reservation_engine_ports,
        )
        self._record_check(report)
        if self._maybe_recovery_backoff(report):
            return
        decision = decide_observer_report(report)
        if decision.confirmation_required:
            confirmation = self._confirm_observer_availability()
            self._record_check(confirmation)
            if self._maybe_recovery_backoff(confirmation):
                return
            decision = decide_observer_confirmation(confirmation)
        if decision.clear_availability_signature:
            self._update_state(availability_signature=None)
        if decision.notify_confirmed_report is not None:
            signature = notify_confirmed_observer_availability(
                self.settings,
                decision.notify_confirmed_report,
            )
            if signature is not None:
                self._update_state(availability_signature=signature)
        if decision.reset_errors:
            self._reset_errors()
            return
        if decision.error_report is not None:
            self._handle_observer_error(decision.error_report)
            return

    def _confirm_observer_availability(self) -> RunReport:
        return run_observer_with_report(
            observer_confirmation_settings(self.settings),
            cancel_event=self._cancel_event,
            capture_captcha_samples=False,
            ports=self._reservation_engine_ports,
        )

    def _observer_captcha_sampling_allowed(self) -> bool:
        try:
            return not list_active_orders(self.settings, include_constrained=False)
        except Exception as exc:
            logger.warning(
                "Stopping observer CAPTCHA sampling because active orders could not be checked: %s",
                exc,
            )
            return False

    def _handle_order_error(
        self,
        order: ServiceOrderCandidate | ServiceOrderRuntime,
        report: RunReport,
    ) -> None:
        self._error_policy.handle_order_error(order, report)

    def _handle_observer_error(self, report: RunReport) -> None:
        self._error_policy.handle_observer_error(report)

    def _handle_rapid_queue_error(self, report: RunReport) -> None:
        self._error_policy.handle_rapid_queue_error(report)

    def _handle_unexpected_error(self, error: Exception) -> None:
        self._error_policy.handle_unexpected_error(error)

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
            if self._process_pending_worker_command():
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
            self._worker_lease.ensure_owned()
            self._stop_event.wait(1)
        return True

    def _interruptible_wait(self, seconds: int) -> None:
        deadline = datetime.now() + timedelta(seconds=max(0, seconds))
        while datetime.now() < deadline and not self._stop_event.is_set():
            if self._daily_cutoff_reached():
                return
            self._worker_lease.ensure_owned()
            if self._process_pending_worker_command():
                return
            with self._guard:
                if self._paused:
                    return
            self._stop_event.wait(min(1, max(0, (deadline - datetime.now()).total_seconds())))

    def _process_pending_worker_command(self) -> bool:
        owner_token = self._worker_lease.owner_token
        if owner_token is None:
            return False
        command = claim_next_worker_command(owner_token=owner_token, settings=self.settings)
        if command is None:
            return False
        try:
            should_stop = self._apply_worker_command(command.command)
        except Exception as exc:
            complete_worker_command(
                command.command_id,
                status="failed",
                error_message=str(exc),
                settings=self.settings,
            )
            raise
        complete_worker_command(command.command_id, status="applied", settings=self.settings)
        logger.info("Applied persisted worker command: %s", command.command)
        return should_stop

    def _apply_worker_command(self, command: str) -> bool:
        if command == "pause":
            self.pause()
            return False
        if command == "resume":
            self.resume()
            return False
        if command == "restart":
            with self._guard:
                self._prepare_restart_state()
            return True
        raise ValueError(f"Unsupported worker command: {command}")

    def _prepare_restart_state(self) -> None:
        self._shutdown_reason = "restart_requested"
        # El reinicio cancela y detiene el ciclo actual, pero no debe convertirse
        # en una pausa persistida que herede el proceso nuevo.
        self._paused = False
        self._cancel_event.set()
        self._stop_event.set()
        self._update_state(
            phase="restarting",
            paused=False,
            next_check_at=None,
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
            self.settings.worker_progress_grace_seconds
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
            expected_owner_token=self._worker_lease.owner_token,
            **changes,
        )

    def _record_check(self, report: RunReport) -> None:
        self._state_callbacks.record_check(report)

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

    def _on_worker_lease_lost(self) -> None:
        with self._guard:
            if self._shutdown_reason not in {DAILY_CUTOFF_REASON, "restart_requested"}:
                self._shutdown_reason = LEASE_LOST_REASON
        self._cancel_event.set()
        self._stop_event.set()

    def _cleanup_once_per_day(self) -> None:
        today = date.today()
        if self._last_cleanup_date == today:
            return
        cleanup_old_files(self.settings)
        self._last_cleanup_date = today

    def _daily_cutoff_reached(self) -> bool:
        return daily_cutoff_reached(self.settings.worker_daily_cutoff_time)

    def _wait_for_hot_window_if_needed(self) -> bool:
        decision = hot_window_wait_decision(
            self.settings,
            extended_until=self._hot_window_extended_until,
        )
        if not decision.should_wait:
            if decision.extended_until is not None:
                self._hot_window_extended_until = decision.extended_until
            if decision.using_extension and self._hot_window_extended_until is not None:
                logger.info(
                    "Continuing in extended hot window until %s",
                    self._hot_window_extended_until.isoformat(timespec="seconds"),
                )
            return False
        self._hot_window_extended_until = decision.extended_until
        wait_seconds = decision.wait_seconds or 1
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
        extended_until = extended_hot_window_until(self.settings)
        if extended_until is None:
            return
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
        defense_signal = portal_defense_signal(report.message)
        if defense_signal is not None:
            wait_seconds = recovery_wait_seconds(self.settings)
            send_telegram_message(
                self.settings,
                "El portal mostro una posible defensa "
                f"({defense_signal}). El worker esperara {wait_seconds} segundos.",
            )
            self._wait_retry(wait_seconds, phase="recovery_backoff")
            self._state_callbacks.reset_unavailable_streak()
            self._reset_errors()
            return True

        limit = self.settings.unavailable_streak_limit
        if limit > 0 and self._state_callbacks.unavailable_streak >= limit:
            wait_seconds = recovery_wait_seconds(self.settings)
            logger.warning(
                "Reached %s consecutive unavailable checks; waiting %s seconds",
                self._state_callbacks.unavailable_streak,
                wait_seconds,
            )
            send_telegram_message(
                self.settings,
                "El worker acumulo muchas respuestas seguidas de Sin Cupos. "
                f"Se pausara {wait_seconds} segundos para bajar la huella.",
            )
            self._wait_retry(wait_seconds, phase="recovery_backoff")
            self._state_callbacks.reset_unavailable_streak()
            self._reset_errors()
            return True
        return False

    def _record_window_metric(self, report: RunReport, *, source: str) -> None:
        details = report.details or {}
        now = datetime.now(WORKER_TIMEZONE)
        window_label = current_window_label(now.time(), self.settings.observer_hot_windows)
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


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _future(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(timespec="seconds")
