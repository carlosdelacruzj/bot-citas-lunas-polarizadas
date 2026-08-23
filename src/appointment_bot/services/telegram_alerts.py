from __future__ import annotations

import logging
import threading
import time
from typing import Any

from appointment_bot.config import Settings
from appointment_bot.core.models import AvailabilityResult
from appointment_bot.db.telegram_alert_outbox import (
    enqueue_telegram_alert,
    mark_telegram_alert_sent,
    next_pending_telegram_alert,
    record_telegram_alert_failure,
    telegram_alert_outbox_status,
)
from appointment_bot.services.notifier import (
    TELEGRAM_URGENT_TIMEOUT_SECONDS,
    format_immediate_availability_message,
    send_telegram_message,
    should_send_immediate_availability,
)
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)
_dispatcher_lock = threading.Lock()
MAX_DELIVERY_ATTEMPTS = 3
PAYLOAD_DETAIL_KEYS = (
    "sede",
    "fecha",
    "hora",
    "date_options",
    "hour_options",
    "cupos",
    "slots",
)


class TelegramAlertDispatcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.telegram_enabled
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled or (self._thread is not None and self._thread.is_alive()):
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="telegram-alert-dispatcher",
            daemon=True,
        )
        self._thread.start()
        try:
            outbox = telegram_alert_outbox_status(settings=self.settings)
        except Exception:
            logger.exception("telegram_alert_outbox_status_failed")
            outbox = {"pending": -1, "sent": -1, "failed": -1, "attempts": -1}
        logger.info("Telegram alert dispatcher started: outbox=%s", outbox)

    def stop(self, *, timeout: float = 6.0) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._wake_event.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("Telegram alert dispatcher did not stop before timeout")
            return
        logger.info("Telegram alert dispatcher stopped")
        self._thread = None

    def enqueue(self, result: AvailabilityResult, *, dedupe_key: str) -> bool:
        if not self.enabled or not should_send_immediate_availability(result):
            return False
        started_at = time.monotonic()
        try:
            enqueue_telegram_alert(
                dedupe_key=dedupe_key,
                payload=_availability_payload(result),
                settings=self.settings,
            )
        except Exception:
            logger.exception("telegram_alert_outbox_persist_failed")
            return False
        self._wake_event.set()
        logger.info(
            "telegram_immediate_alert_queued dedupe_key=%s enqueue_ms=%.1f",
            dedupe_key[:12],
            (time.monotonic() - started_at) * 1000,
        )
        return True

    def enqueue_message(self, message: str, *, dedupe_key: str) -> bool:
        if not self.enabled:
            return False
        try:
            enqueue_telegram_alert(
                dedupe_key=dedupe_key,
                payload={"message": sanitize_text(message)[:1000]},
                settings=self.settings,
            )
        except Exception:
            logger.exception("telegram_alert_outbox_persist_failed")
            return False
        self._wake_event.set()
        logger.info("telegram_generic_alert_queued dedupe_key=%s", dedupe_key[:24])
        return True

    def _run(self) -> None:
        while not self._stop_event.is_set():
            row = self._next_pending()
            if row is None:
                self._wake_event.wait(0.5)
                self._wake_event.clear()
                continue
            self._deliver(row)

    def _next_pending(self) -> dict[str, Any] | None:
        try:
            return next_pending_telegram_alert(settings=self.settings)
        except Exception:
            logger.exception("telegram_alert_outbox_read_failed")
            self._stop_event.wait(1.0)
            return None

    def _deliver(self, row: dict[str, Any]) -> None:
        dedupe_key = str(row["dedupe_key"])
        payload = dict(row["payload"])
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            delivered = send_telegram_message(
                self.settings,
                sanitize_text(message)[:1000],
                timeout_seconds=TELEGRAM_URGENT_TIMEOUT_SECONDS,
            )
        else:
            result = AvailabilityResult(
                status=str(payload.get("status") or "available"),
                message="",
                details=dict(payload.get("details") or {}),
            )
            delivered = send_telegram_message(
                self.settings,
                format_immediate_availability_message(result),
                timeout_seconds=TELEGRAM_URGENT_TIMEOUT_SECONDS,
            )
        if delivered:
            try:
                mark_telegram_alert_sent(dedupe_key, settings=self.settings)
            except Exception:
                logger.exception(
                    "telegram_alert_sent_persist_failed dedupe_key=%s",
                    dedupe_key[:12],
                )
                self._stop_event.wait(1.0)
                return
            logger.info("telegram_immediate_alert_sent dedupe_key=%s", dedupe_key[:12])
            return
        try:
            exhausted, delay_seconds = record_telegram_alert_failure(
                dedupe_key,
                attempt_count=int(row["attempt_count"]),
                max_attempts=MAX_DELIVERY_ATTEMPTS,
                error="telegram_delivery_failed",
                settings=self.settings,
            )
        except Exception:
            logger.exception(
                "telegram_alert_failure_persist_failed dedupe_key=%s",
                dedupe_key[:12],
            )
            self._stop_event.wait(1.0)
            return
        if exhausted:
            logger.error(
                "telegram_immediate_alert_failed dedupe_key=%s attempts=%s",
                dedupe_key[:12],
                MAX_DELIVERY_ATTEMPTS,
            )
        else:
            logger.warning(
                "telegram_immediate_alert_deferred dedupe_key=%s retry_seconds=%s",
                dedupe_key[:12],
                delay_seconds,
            )


def _availability_payload(result: AvailabilityResult) -> dict[str, Any]:
    source_details = result.details or {}
    details = {
        key: _safe_payload_value(source_details[key])
        for key in PAYLOAD_DETAIL_KEYS
        if source_details.get(key) is not None
    }
    return {"status": result.status, "details": details}


def _safe_payload_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_payload_value(item) for item in value]
    return sanitize_text(str(value))


_dispatcher: TelegramAlertDispatcher | None = None


def configure_telegram_alerts(settings: Settings) -> TelegramAlertDispatcher:
    global _dispatcher
    with _dispatcher_lock:
        if _dispatcher is not None:
            _dispatcher.stop()
        _dispatcher = TelegramAlertDispatcher(settings)
        return _dispatcher


def enqueue_immediate_availability(
    result: AvailabilityResult,
    *,
    dedupe_key: str,
) -> bool:
    with _dispatcher_lock:
        dispatcher = _dispatcher
    if dispatcher is None:
        logger.error("Telegram alert dispatcher is not configured")
        return False
    return dispatcher.enqueue(result, dedupe_key=dedupe_key)


def enqueue_generic_telegram_alert(message: str, *, dedupe_key: str) -> bool:
    with _dispatcher_lock:
        dispatcher = _dispatcher
    if dispatcher is None:
        logger.error("Telegram alert dispatcher is not configured")
        return False
    return dispatcher.enqueue_message(message, dedupe_key=dedupe_key)
