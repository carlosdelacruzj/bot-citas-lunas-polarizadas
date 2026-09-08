from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from appointment_bot.configuration.reservation import ReservationSettings
from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.configuration.telegram import TelegramSettings
from appointment_bot.core.models import RunReport, ServiceOrderRuntime
from appointment_bot.db.orders import update_order_state
from appointment_bot.services.notifier import send_telegram_message
from appointment_bot.worker.recovery import is_network_error, portal_defense_signal

logger = logging.getLogger(__name__)


class WorkerErrorPolicy:
    def __init__(
        self,
        *,
        increase_errors: Callable[[str], int],
        reset_errors: Callable[[], None],
        wait_retry: Callable[[int], None],
        wait_retry_phase: Callable[[int, str], None],
        wait_for_backoff: Callable[[ServiceOrderRuntime, int], None],
        stop_event: threading.Event,
        runtime_settings: RuntimeSettings,
        reservation_settings: ReservationSettings,
        telegram_settings: TelegramSettings,
    ) -> None:
        self.runtime_settings = runtime_settings
        self.reservation_settings = reservation_settings
        self.telegram_settings = telegram_settings
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
                backoff_seconds=self.runtime_settings.error_backoff_seconds,
                settings=self.runtime_settings,
            )
            send_telegram_message(
                (
                    "El portal mostro una posible defensa durante el "
                    "monitoreo ("
                    f"{defense_signal}"
                    ") para "
                    f"{order.order_id}"
                    ". El worker esperara "
                    f"{self.runtime_settings.error_backoff_seconds}"
                    " segundos."
                ),
                telegram_settings=self.telegram_settings,
            )
            self._wait_retry_phase(self.runtime_settings.error_backoff_seconds, "backoff")
            self._reset_errors()
            return
        failures = self._increase_errors(report.message)
        if report.status == "reservation_unconfirmed":
            self.apply_order_backoff(order, report)
            return
        if is_network_error(report.message) and failures <= len(
            self.reservation_settings.session_retry_delays_seconds
        ):
            delay = self.reservation_settings.session_retry_delays_seconds[failures - 1]
            self._wait_retry(delay)
            return
        self.apply_order_backoff(order, report)

    def handle_observer_error(self, report: RunReport) -> None:
        failures = self._increase_errors(report.message)
        if failures <= len(self.reservation_settings.session_retry_delays_seconds):
            self._wait_retry(self.reservation_settings.session_retry_delays_seconds[failures - 1])
            return
        send_telegram_message(
            (
                "El observador continuo acumulo fallos. Reintenta"
                "ra en "
                f"{self.runtime_settings.error_backoff_seconds}"
                " segundos."
            ),
            telegram_settings=self.telegram_settings,
        )
        self._wait_retry_phase(self.runtime_settings.error_backoff_seconds, "backoff")
        self._reset_errors()

    def handle_rapid_queue_error(self, report: RunReport) -> None:
        failures = self._increase_errors(report.message)
        if failures <= len(self.reservation_settings.session_retry_delays_seconds):
            self._wait_retry(self.reservation_settings.session_retry_delays_seconds[failures - 1])
            return
        self._wait_retry_phase(self.runtime_settings.error_backoff_seconds, "backoff")
        self._reset_errors()

    def handle_unexpected_error(self, error: Exception) -> None:
        try:
            failures = self._increase_errors(str(error))
        except Exception:
            logger.exception("Could not persist unexpected worker failure")
            self._stop_event.wait(self.runtime_settings.error_backoff_seconds)
            return
        delays = self.reservation_settings.session_retry_delays_seconds
        if failures <= len(delays):
            self._wait_retry(delays[failures - 1])
            return
        send_telegram_message(
            (
                "El trabajador continuo encontro tres fallos inte"
                "rnos. Reintentara en "
                f"{self.runtime_settings.error_backoff_seconds}"
                " segundos."
            ),
            telegram_settings=self.telegram_settings,
        )
        self._wait_retry_phase(self.runtime_settings.error_backoff_seconds, "backoff")
        self._reset_errors()

    def apply_order_backoff(self, order: ServiceOrderRuntime, report: RunReport) -> None:
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=1,
            backoff_seconds=self.runtime_settings.error_backoff_seconds,
            settings=self.runtime_settings,
        )
        send_telegram_message(
            (
                "La orden "
                f"{order.order_id}"
                " entro en backoff por errores consecutivos. Se c"
                "onserva su prioridad y no se procesaran ordenes "
                "posteriores."
            ),
            telegram_settings=self.telegram_settings,
        )
        self._wait_for_backoff(order, self.runtime_settings.error_backoff_seconds)
        self._reset_errors()
