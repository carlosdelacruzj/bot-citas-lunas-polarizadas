from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from appointment_bot.config import Settings
from appointment_bot.db.orders import update_order_state
from appointment_bot.domain import RunReport
from appointment_bot.services.database_models import ServiceOrderRuntime
from appointment_bot.services.notifier import send_telegram_message
from appointment_bot.services.worker_recovery import is_network_error, portal_defense_signal

logger = logging.getLogger(__name__)


class WorkerErrorPolicy:
    def __init__(
        self,
        settings: Settings,
        *,
        increase_errors: Callable[[str], int],
        reset_errors: Callable[[], None],
        wait_retry: Callable[[int], None],
        wait_retry_phase: Callable[[int, str], None],
        wait_for_backoff: Callable[[ServiceOrderRuntime, int], None],
        stop_event: threading.Event,
    ) -> None:
        self.settings = settings
        self._increase_errors = increase_errors
        self._reset_errors = reset_errors
        self._wait_retry = wait_retry
        self._wait_retry_phase = wait_retry_phase
        self._wait_for_backoff = wait_for_backoff
        self._stop_event = stop_event

    def handle_order_error(self, order: ServiceOrderRuntime, report: RunReport) -> None:
        defense_signal = portal_defense_signal(report.message)
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
            self._wait_retry_phase(self.settings.error_backoff_seconds, "backoff")
            self._reset_errors()
            return
        failures = self._increase_errors(report.message)
        if report.status == "reservation_unconfirmed":
            self.apply_order_backoff(order, report)
            return
        if is_network_error(report.message) and failures <= len(
            self.settings.session_retry_delays_seconds
        ):
            delay = self.settings.session_retry_delays_seconds[failures - 1]
            self._wait_retry(delay)
            return
        self.apply_order_backoff(order, report)

    def handle_observer_error(self, report: RunReport) -> None:
        failures = self._increase_errors(report.message)
        if failures <= len(self.settings.session_retry_delays_seconds):
            self._wait_retry(self.settings.session_retry_delays_seconds[failures - 1])
            return
        send_telegram_message(
            self.settings,
            "El observador continuo acumulo fallos. "
            f"Reintentara en {self.settings.error_backoff_seconds} segundos.",
        )
        self._wait_retry_phase(self.settings.error_backoff_seconds, "backoff")
        self._reset_errors()

    def handle_rapid_queue_error(self, report: RunReport) -> None:
        failures = self._increase_errors(report.message)
        if failures <= len(self.settings.session_retry_delays_seconds):
            self._wait_retry(self.settings.session_retry_delays_seconds[failures - 1])
            return
        self._wait_retry_phase(self.settings.error_backoff_seconds, "backoff")
        self._reset_errors()

    def handle_unexpected_error(self, error: Exception) -> None:
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
        self._wait_retry_phase(self.settings.error_backoff_seconds, "backoff")
        self._reset_errors()

    def apply_order_backoff(self, order: ServiceOrderRuntime, report: RunReport) -> None:
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
