from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
    should_send_immediate_availability,
)
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)
_dispatcher_lock = threading.Lock()
MAX_DELIVERY_ATTEMPTS = 3
MAX_GENERIC_MESSAGE_LENGTH = 1000
GENERIC_ALERT_CAPTCHA_PREFIX = "captcha-graphic-returned:"
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

    def enqueue_message(
        self,
        message: str,
        *,
        dedupe_key: str,
        operator_forward: bool = False,
        order_id: str | None = None,
        navigation: str | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        try:
            enqueue_telegram_alert(
                dedupe_key=dedupe_key,
                payload=_generic_alert_payload(
                    message,
                    dedupe_key=dedupe_key,
                    operator_forward=operator_forward,
                    order_id=order_id,
                    navigation=navigation,
                ),
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
            delivered = _send_alert_message(
                self.settings,
                _format_generic_alert(payload),
                reply_markup=_navigation_markup(payload),
                timeout_seconds=TELEGRAM_URGENT_TIMEOUT_SECONDS,
            )
        else:
            result = AvailabilityResult(
                status=str(payload.get("status") or "available"),
                message="",
                details=dict(payload.get("details") or {}),
            )
            delivered = _send_alert_message(
                self.settings,
                format_immediate_availability_message(result),
                reply_markup=_navigation_markup(payload),
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
    return {
        "status": result.status,
        "details": details,
        "alert_kind": "availability",
        "navigation": "status",
    }


def _generic_alert_payload(
    message: str,
    *,
    dedupe_key: str,
    operator_forward: bool,
    order_id: str | None,
    navigation: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": sanitize_text(message)[:MAX_GENERIC_MESSAGE_LENGTH],
        "alert_kind": "operator_forward" if operator_forward else "operational",
    }
    if dedupe_key.startswith(GENERIC_ALERT_CAPTCHA_PREFIX):
        payload["alert_kind"] = "captcha_graphic_returned"
        payload["navigation"] = "status"
    elif navigation in {"client", "payments", "status"}:
        payload["navigation"] = navigation
    if order_id and _valid_order_id(order_id):
        payload["order_id"] = order_id
        if navigation is None:
            payload["navigation"] = "client"
    return payload


def _format_generic_alert(payload: dict[str, Any]) -> str:
    message = sanitize_text(str(payload.get("message") or "")).strip()
    kind = str(payload.get("alert_kind") or "operational")
    if kind == "captcha_graphic_returned":
        return (
            "CAMBIO EN EL CAPTCHA DEL PORTAL\n\n"
            "El portal volvió a mostrar un CAPTCHA gráfico.\n\n"
            "Reserva: continuará usando 2Captcha.\n"
            "V3/V6: permanecen en reserva fría.\n\n"
            "Acción: revisa el cambio antes de reactivar V3/V6."
        )
    if kind == "operator_forward":
        return f"TEXTO PARA ENVIAR AL CLIENTE\n\n{message}"
    return f"AVISO OPERATIVO - NO REENVIAR\n\n{message}"


def _navigation_markup(payload: dict[str, Any]) -> dict[str, Any] | None:
    navigation = str(payload.get("navigation") or "")
    order_id = str(payload.get("order_id") or "")
    if navigation == "client" and _valid_order_id(order_id):
        button = {"text": "Ver cliente", "callback_data": f"om:{order_id}:show"}
    elif navigation == "payments":
        button = {"text": "Cobros pendientes", "callback_data": "ui:payments:1"}
    elif navigation == "status":
        button = {"text": "Estado del sistema", "callback_data": "ui:status:show"}
    else:
        return None
    if len(str(button["callback_data"]).encode("utf-8")) > 64:
        return None
    return {"inline_keyboard": [[button]]}


def _valid_order_id(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value) is not None


def _send_alert_message(
    settings: Settings,
    message: str,
    *,
    reply_markup: dict[str, Any] | None,
    timeout_seconds: int,
) -> bool:
    if not settings.telegram_enabled:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": settings.telegram_chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning("Could not send Telegram alert: %s", exc)
        return False
    try:
        data = json.loads(response_body)
    except json.JSONDecodeError:
        logger.warning("Telegram returned a non-JSON alert response")
        return False
    if not data.get("ok"):
        logger.warning("Telegram rejected alert: %s", data)
        return False
    logger.info("Telegram alert sent")
    return True


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


def enqueue_generic_telegram_alert(
    message: str,
    *,
    dedupe_key: str,
    operator_forward: bool = False,
    order_id: str | None = None,
    navigation: str | None = None,
) -> bool:
    with _dispatcher_lock:
        dispatcher = _dispatcher
    if dispatcher is None:
        logger.error("Telegram alert dispatcher is not configured")
        return False
    return dispatcher.enqueue_message(
        message,
        dedupe_key=dedupe_key,
        operator_forward=operator_forward,
        order_id=order_id,
        navigation=navigation,
    )
