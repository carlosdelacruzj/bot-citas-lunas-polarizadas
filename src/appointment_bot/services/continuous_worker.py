from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult, RunReport
from appointment_bot.main import run_with_report
from appointment_bot.services.cleanup import cleanup_old_files
from appointment_bot.services.client_runtime import (
    report_is_programmed,
    settings_with_client_state_dir,
)
from appointment_bot.services.client_transitions import (
    client_can_submit,
    reconcile_pending_submission,
)
from appointment_bot.services.database import (
    Client,
    client_backoff_seconds,
    client_reservation_pending,
    get_worker_state,
    list_active_clients,
    mark_client_done,
    mark_client_submission_intent,
    mark_client_submission_pending,
    update_client_state,
    update_worker_state,
)
from appointment_bot.services.notifier import notify_result, send_telegram_message
from appointment_bot.services.observer import run_observer_with_report
from appointment_bot.services.queue_runner import run_rapid_queue_with_settings
from appointment_bot.services.run_reporting import settings_for_client
from appointment_bot.services.runtime import single_run_lock
from appointment_bot.utils.sanitization import sanitize_text

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
        self._owner_token: str | None = None
        self._last_cleanup_date: date | None = None

    @property
    def is_running(self) -> bool:
        with self._guard:
            return self._running

    @property
    def is_starting_or_running(self) -> bool:
        with self._guard:
            return self._starting or self._running

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

    def stop(self) -> None:
        self._stop_event.set()
        self._cancel_event.set()

    def run_forever(self) -> None:
        with self._guard:
            if self._starting or self._running:
                raise RuntimeError("Continuous worker is already running.")
            self._starting = True

        lock_acquired = False
        try:
            # El lock se conserva durante toda la vida del trabajador para
            # impedir un segundo servicio o una ejecucion manual simultanea.
            with single_run_lock(self.settings) as process_lock:
                lock_acquired = True
                self._owner_token = process_lock.owner_token
                with self._guard:
                    self._starting = False
                    self._running = True
                update_worker_state(
                    self.settings,
                    phase="paused" if self._paused else "starting",
                    paused=self._paused,
                    last_error=None,
                    last_check_at=_now(),
                    owner_token=self._owner_token,
                )
                self._ready_event.set()
                while not self._stop_event.is_set():
                    self._cleanup_once_per_day()
                    if self._wait_while_paused():
                        break
                    try:
                        clients = list_active_clients(self.settings)
                        if clients:
                            self._monitor_client(clients[0])
                        else:
                            self._monitor_observer()
                    except Exception as exc:
                        logger.exception("Unexpected continuous worker cycle failure")
                        self._handle_unexpected_error(exc)
        finally:
            if lock_acquired and self._owner_token is not None:
                try:
                    update_worker_state(
                        self.settings,
                        expected_owner_token=self._owner_token,
                        phase="stopped",
                        current_client_id=None,
                        masked_account=None,
                        session_started_at=None,
                        next_check_at=None,
                        owner_token=None,
                    )
                except RuntimeError:
                    logger.warning("Worker state ownership changed before shutdown.")
            with self._guard:
                self._starting = False
                self._running = False
                self._ready_event.set()

    def _monitor_client(self, client: Client) -> None:
        previous_state = get_worker_state(self.settings)
        client_settings = self._continuous_client_settings(client)
        if (
            previous_state.current_client_id not in {None, client.client_id}
            or previous_state.phase == "monitoring_observer"
            or (
                previous_state.masked_account is not None
                and previous_state.masked_account != client_settings.safe_username
            )
        ):
            self._reset_errors()
        backoff = client_backoff_seconds(client.client_id, settings=self.settings)
        if backoff > 0:
            self._wait_for_backoff(client, backoff)
            return

        pending_submission = client_reservation_pending(
            client.client_id,
            settings=self.settings,
        )
        cycle_settings = (
            replace(client_settings, auto_reserve=False) if pending_submission else client_settings
        )
        self._set_session_state("monitoring_client", client.client_id, cycle_settings.safe_username)
        report = run_with_report(
            cycle_settings,
            client_id=client.client_id,
            use_lock=False,
            apply_jitter=False,
            cleanup_files=False,
            record_history=True,
            cancel_event=self._cancel_event,
            use_run_state=False,
            enforce_run_timeout=False,
            on_check=self._on_client_check,
            can_submit=lambda: client_can_submit(client.client_id, self.settings),
            on_submission_intent=lambda: mark_client_submission_intent(
                client.client_id,
                settings=self.settings,
            ),
            on_submission_started=lambda: mark_client_submission_pending(
                client.client_id,
                settings=self.settings,
            ),
        )
        self._record_check(report)
        if report.status == "paused":
            return
        if report_is_programmed(report):
            mark_client_done(client.client_id, status="programmed", settings=self.settings)
            self._reset_errors()
            return
        if report.status == "registered":
            mark_client_done(client.client_id, settings=self.settings)
            self._increment_confirmed()
            self._reset_errors()
            self._run_rapid_queue()
            return
        if pending_submission:
            if reconcile_pending_submission(client.client_id, report, self.settings):
                self._reset_errors()
                return
            report = RunReport(
                status="reservation_unconfirmed",
                message=(
                    "Existe un envio de reserva pendiente. Se verifico el portal sin "
                    "intentar una nueva reserva."
                ),
                exit_code=1,
                client_id=client.client_id,
                details=report.details,
            )
            self._handle_client_error(client, report)
            return
        if report.status in {"unavailable", "partial", "available", "completed"}:
            self._reset_errors()
            update_client_state(
                client.client_id,
                status=report.status,
                message=report.message,
                exit_code=report.exit_code,
                settings=self.settings,
            )
            # Al terminar los 25 minutos se renueva la sesion, pero el
            # mismo cliente conserva la prioridad y vuelve a abrirse inmediatamente.
            return
        self._handle_client_error(client, report)

    def _run_rapid_queue(self) -> None:
        update_worker_state(
            self.settings,
            phase="rapid_queue",
            current_client_id=None,
            masked_account=None,
            session_started_at=None,
        )
        report = run_rapid_queue_with_settings(
            self.settings,
            initial_confirmed_reservations=1,
            cancel_event=self._cancel_event,
            on_client_start=self._on_rapid_client_start,
        )
        confirmed = int((report.details or {}).get("confirmed_reservations", 0))
        if confirmed:
            self._increment_confirmed(confirmed)
        if report.status == "paused":
            return
        if report.exit_code != 0:
            self._handle_rapid_queue_error(report)

    def _monitor_observer(self) -> None:
        previous_state = get_worker_state(self.settings)
        cycle_settings = self._continuous_settings(self.settings)
        if previous_state.current_client_id is not None or (
            previous_state.masked_account is not None
            and previous_state.masked_account != cycle_settings.safe_username
        ):
            self._reset_errors()
        self._set_session_state("monitoring_observer", None, cycle_settings.safe_username)
        report = run_observer_with_report(
            cycle_settings,
            use_lock=False,
            diagnostic=False,
            visible=False,
            notify=False,
            cancel_event=self._cancel_event,
            enforce_run_timeout=False,
            on_check=self._on_observer_check,
        )
        self._record_check(report)
        if report.status == "paused":
            return
        if report.status == "available":
            confirmation = self._confirm_observer_availability()
            self._record_check(confirmation)
            if confirmation.status != "available":
                update_worker_state(self.settings, availability_signature=None)
                if confirmation.status in {"unavailable", "partial"}:
                    self._reset_errors()
                    return
                self._handle_observer_error(confirmation)
                return
            self._notify_confirmed_observer_availability(confirmation)
            self._reset_errors()
            return
        if report.status in {"unavailable", "partial"}:
            update_worker_state(self.settings, availability_signature=None)
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
            use_lock=False,
            diagnostic=False,
            visible=False,
            notify=False,
            record_history=True,
            cancel_event=self._cancel_event,
            enforce_run_timeout=False,
        )

    def _notify_confirmed_observer_availability(self, report: RunReport) -> None:
        signature = _availability_signature(report)
        state = get_worker_state(self.settings)
        if signature == state.availability_signature:
            return
        result = AvailabilityResult(
            status=report.status,
            message=report.message,
            details=report.details,
        )
        screenshot_path = Path(report.screenshot_path) if report.screenshot_path else None
        delivered = notify_result(result, self.settings, screenshot_path)
        if delivered or not self.settings.telegram_enabled:
            update_worker_state(self.settings, availability_signature=signature)

    def _handle_client_error(self, client: Client, report: RunReport) -> None:
        failures = self._increase_errors(report.message)
        if report.status == "reservation_unconfirmed":
            self._apply_client_backoff(client, report)
            return
        if failures <= len(self.settings.session_retry_delays_seconds):
            delay = self.settings.session_retry_delays_seconds[failures - 1]
            self._wait_retry(delay)
            return
        self._apply_client_backoff(client, report)

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

    def _apply_client_backoff(self, client: Client, report: RunReport) -> None:
        update_client_state(
            client.client_id,
            status=report.status,
            message=report.message,
            exit_code=1,
            backoff_seconds=self.settings.error_backoff_seconds,
            settings=self.settings,
        )
        send_telegram_message(
            self.settings,
            f"El cliente {client.client_id} entro en backoff por errores consecutivos. "
            "Se conserva su prioridad y no se procesaran clientes posteriores.",
        )
        self._wait_for_backoff(client, self.settings.error_backoff_seconds)
        self._reset_errors()

    def _wait_for_backoff(self, client: Client, seconds: int) -> None:
        update_worker_state(
            self.settings,
            phase="backoff",
            current_client_id=client.client_id,
            next_check_at=_future(seconds),
        )
        self._interruptible_wait(seconds)

    def _wait_retry(self, seconds: int, *, phase: str = "retry_wait") -> None:
        update_worker_state(
            self.settings,
            phase=phase,
            session_started_at=None,
            next_check_at=_future(seconds),
        )
        self._interruptible_wait(seconds)

    def _wait_while_paused(self) -> bool:
        while not self._stop_event.is_set():
            with self._guard:
                paused = self._paused
            if not paused:
                self._cancel_event.clear()
                return False
            update_worker_state(
                self.settings,
                phase="paused",
                paused=True,
                session_started_at=None,
                next_check_at=None,
            )
            self._stop_event.wait(1)
        return True

    def _interruptible_wait(self, seconds: int) -> None:
        deadline = datetime.now() + timedelta(seconds=max(0, seconds))
        while datetime.now() < deadline and not self._stop_event.is_set():
            with self._guard:
                if self._paused:
                    return
            self._stop_event.wait(min(1, max(0, (deadline - datetime.now()).total_seconds())))

    def _continuous_client_settings(self, client: Client) -> Settings:
        settings = settings_for_client(
            self.settings,
            username=client.username,
            password=client.password,
        )
        settings = settings_with_client_state_dir(settings, client)
        return self._continuous_settings(settings)

    def _continuous_settings(self, settings: Settings) -> Settings:
        return replace(
            settings,
            monitor_window_seconds=settings.session_rotation_seconds,
            monitor_max_attempts=1_000_000,
            monitor_interval_min_seconds=settings.continuous_interval_min_seconds,
            monitor_interval_max_seconds=settings.continuous_interval_max_seconds,
        )

    def _set_session_state(
        self,
        phase: str,
        client_id: str | None,
        masked_account: str,
    ) -> None:
        update_worker_state(
            self.settings,
            phase=phase,
            paused=False,
            current_client_id=client_id,
            masked_account=masked_account,
            session_started_at=_now(),
            next_check_at=_now(),
        )

    def health(self) -> tuple[bool, str]:
        if not self.is_running:
            return False, "worker_stopped"
        state = get_worker_state(self.settings)
        if state.paused or state.phase in {"paused", "backoff", "retry_wait"}:
            return True, state.phase
        timestamp = state.last_check_at or state.session_started_at or state.updated_at
        if not timestamp:
            return False, "worker_has_no_progress_timestamp"
        try:
            age_seconds = (datetime.now() - datetime.fromisoformat(timestamp)).total_seconds()
        except ValueError:
            return False, "worker_progress_timestamp_invalid"
        stale_after = max(
            180,
            self.settings.continuous_interval_max_seconds
            + self.settings.login_timeout_seconds
            + self.settings.postback_timeout_seconds
            + self.settings.read_timeout_seconds
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
        update_worker_state(
            self.settings,
            last_check_at=_now(),
            next_check_at=None,
            last_error=sanitize_text(report.message) if report.exit_code else None,
        )

    def _on_client_check(
        self,
        result: AvailabilityResult,
        attempt: int,
        next_check_seconds: int | None,
    ) -> None:
        if result.status not in {"error", "unknown", "reservation_unconfirmed"}:
            self._reset_errors(clear_session=False)
        update_worker_state(
            self.settings,
            last_check_at=_now(),
            next_check_at=(_future(next_check_seconds) if next_check_seconds is not None else None),
        )

    def _on_rapid_client_start(self, client: Client) -> None:
        client_settings = self._continuous_client_settings(client)
        update_worker_state(
            self.settings,
            phase="rapid_queue",
            current_client_id=client.client_id,
            masked_account=client_settings.safe_username,
            session_started_at=_now(),
            next_check_at=_now(),
        )

    def _on_observer_check(
        self,
        result: AvailabilityResult,
        screenshot_path: Path | None,
        attempt: int,
        next_check_seconds: int | None,
    ) -> None:
        if result.status not in {"error", "unknown", "reservation_unconfirmed"}:
            self._reset_errors(clear_session=False)
        update_worker_state(
            self.settings,
            last_check_at=_now(),
            next_check_at=(_future(next_check_seconds) if next_check_seconds is not None else None),
        )
        if result.status != "available":
            if result.status == "unavailable":
                update_worker_state(self.settings, availability_signature=None)
            return

    def _increase_errors(self, message: str) -> int:
        message = sanitize_text(message)
        state = get_worker_state(self.settings)
        failures = state.consecutive_errors + 1
        update_worker_state(
            self.settings,
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
        update_worker_state(self.settings, **changes)

    def _increment_confirmed(self, amount: int = 1) -> None:
        state = get_worker_state(self.settings)
        update_worker_state(
            self.settings,
            confirmed_reservations=state.confirmed_reservations + amount,
        )

    def _cleanup_once_per_day(self) -> None:
        today = date.today()
        if self._last_cleanup_date == today:
            return
        cleanup_old_files(self.settings)
        self._last_cleanup_date = today


def _availability_signature(report: RunReport) -> str:
    details = report.details or {}
    relevant = {
        key: details.get(key)
        for key in ("sede", "fecha", "hora", "date_options", "hour_options")
        if details.get(key) is not None
    }
    payload = json.dumps(_normalize_signature_value(relevant), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_signature_value(value):
    if isinstance(value, dict):
        return {key: _normalize_signature_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        normalized = [_normalize_signature_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _future(seconds: int) -> str:
    return (datetime.now() + timedelta(seconds=seconds)).isoformat(timespec="seconds")
