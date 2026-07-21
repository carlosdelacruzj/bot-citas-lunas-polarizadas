from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from appointment_bot.config import Settings
from appointment_bot.db.captcha_shadow_outbox import (
    captcha_shadow_outbox_status,
    defer_captcha_shadow_event,
    mark_captcha_shadow_event_processed,
    next_pending_captcha_shadow_event,
    persist_captcha_shadow_event,
)

logger = logging.getLogger(__name__)
_dispatcher_lock = threading.Lock()
CAPTCHA_ANSWER_PATTERN = re.compile(r"[A-Z0-9]{5}")


@dataclass(frozen=True)
class CaptchaShadowEvent:
    endpoint: str
    payload: dict[str, Any]
    event_key: str = ""
    sequence: int = 1
    attempt_count: int = 0


class CaptchaShadowDispatcher:
    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        max_queue_size: int,
        timeout_seconds: int,
        settings: Settings | None = None,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.settings = settings
        self._events: queue.Queue[CaptchaShadowEvent] = queue.Queue(
            maxsize=max_queue_size
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._counters_lock = threading.Lock()
        self._counters = {
            "enqueued": 0,
            "processed": 0,
            "failed": 0,
            "discarded": 0,
            "durable": 0,
            "recovered": 0,
        }

    @classmethod
    def from_settings(cls, settings: Settings) -> CaptchaShadowDispatcher:
        enabled = settings.captcha_shadow_enabled
        if enabled and not _is_local_http_url(settings.captcha_shadow_url):
            logger.error(
                "CAPTCHA shadow disabled because URL is not local HTTP: %s",
                settings.captcha_shadow_url,
            )
            enabled = False
        return cls(
            enabled=enabled,
            base_url=settings.captcha_shadow_url,
            max_queue_size=settings.captcha_shadow_queue_size,
            timeout_seconds=settings.captcha_shadow_timeout_seconds,
            settings=settings,
        )

    def start(self) -> None:
        if not self.enabled or (self._thread is not None and self._thread.is_alive()):
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="captcha-shadow-dispatcher",
            daemon=True,
        )
        self._thread.start()
        try:
            outbox = (
                captcha_shadow_outbox_status(settings=self.settings)
                if self.settings is not None
                else {"pending": 0, "processed": 0, "attempts": 0}
            )
        except Exception:
            logger.exception("captcha_shadow_outbox_status_failed")
            outbox = {"pending": -1, "processed": -1, "attempts": -1}
        logger.info(
            "CAPTCHA shadow dispatcher started: %s outbox=%s",
            self.base_url,
            outbox,
        )

    def stop(self, *, timeout: float = 2.0) -> None:
        if self._thread is None:
            return
        deadline = time.monotonic() + max(timeout, 0.0)
        while self._events.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.02)
        self._stop_event.set()
        self._thread.join(timeout=max(deadline - time.monotonic(), 0.0))
        if self._thread.is_alive():
            logger.warning("CAPTCHA shadow dispatcher did not stop before timeout")
        else:
            logger.info("CAPTCHA shadow dispatcher stopped: %s", self.status())
            self._thread = None

    def enqueue(self, event: CaptchaShadowEvent) -> bool:
        if not self.enabled:
            return False
        durable = self._persist(event)
        try:
            self._events.put_nowait(event)
        except queue.Full:
            if durable:
                logger.info(
                    "captcha_shadow_queued_durably event_id=%s",
                    event.payload.get("event_id", "<missing>"),
                )
                return True
            self._increment("discarded")
            logger.warning(
                "captcha_shadow_queue_full event_id=%s",
                event.payload.get("event_id", "<missing>"),
            )
            return False
        self._increment("enqueued")
        return True

    def status(self) -> dict[str, int | bool]:
        with self._counters_lock:
            counters = dict(self._counters)
        return {
            "enabled": self.enabled,
            "running": bool(self._thread and self._thread.is_alive()),
            "queued": self._events.qsize(),
            **counters,
        }

    def _run(self) -> None:
        next_outbox_poll = 0.0
        while not self._stop_event.is_set():
            try:
                event = self._events.get(timeout=0.2)
            except queue.Empty:
                if self.settings is None or time.monotonic() < next_outbox_poll:
                    continue
                next_outbox_poll = time.monotonic() + 1.0
                event = self._next_durable_event()
                if event is None:
                    continue
                self._increment("recovered")
                self._safe_process_event(event)
                continue
            try:
                self._safe_process_event(event)
            finally:
                self._events.task_done()

    def _safe_process_event(self, event: CaptchaShadowEvent) -> None:
        try:
            self._process_event(event)
        except Exception:
            self._increment("failed")
            logger.exception(
                "captcha_shadow_unexpected_error event_id=%s",
                event.payload.get("event_id", "<missing>"),
            )

    def _process_event(self, event: CaptchaShadowEvent) -> None:
        try:
            self._send(event)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            self._increment("failed")
            if self.settings is not None and event.event_key:
                delay = defer_captcha_shadow_event(
                    event.event_key,
                    attempt_count=event.attempt_count,
                    error=str(exc),
                    settings=self.settings,
                )
                logger.warning(
                    "captcha_shadow_request_deferred endpoint=%s event_id=%s "
                    "retry_seconds=%s error=%s",
                    event.endpoint,
                    event.payload.get("event_id", "<missing>"),
                    delay,
                    exc,
                )
                return
            logger.warning(
                "captcha_shadow_request_failed endpoint=%s event_id=%s error=%s",
                event.endpoint,
                event.payload.get("event_id", "<missing>"),
                exc,
            )
            return
        if self.settings is not None and event.event_key:
            mark_captcha_shadow_event_processed(
                event.event_key,
                settings=self.settings,
            )
        self._increment("processed")
        logger.info(
            "captcha_shadow_request_completed endpoint=%s event_id=%s",
            event.endpoint,
            event.payload.get("event_id", "<missing>"),
        )

    def _send(self, event: CaptchaShadowEvent) -> None:
        request = Request(
            f"{self.base_url}{event.endpoint}",
            data=json.dumps(event.payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            response.read()

    def _persist(self, event: CaptchaShadowEvent) -> bool:
        if self.settings is None or not event.event_key:
            return False
        try:
            persist_captcha_shadow_event(
                event_key=event.event_key,
                event_id=str(event.payload.get("event_id") or ""),
                sequence=event.sequence,
                endpoint=event.endpoint,
                payload=event.payload,
                settings=self.settings,
            )
        except Exception:
            logger.exception(
                "captcha_shadow_outbox_persist_failed event_id=%s",
                event.payload.get("event_id", "<missing>"),
            )
            return False
        self._increment("durable")
        return True

    def _next_durable_event(self) -> CaptchaShadowEvent | None:
        if self.settings is None:
            return None
        try:
            row = next_pending_captcha_shadow_event(settings=self.settings)
        except Exception:
            logger.exception("captcha_shadow_outbox_read_failed")
            return None
        if row is None:
            return None
        return CaptchaShadowEvent(
            endpoint=str(row["endpoint"]),
            payload=dict(row["payload"]),
            event_key=str(row["event_key"]),
            sequence=int(row["sequence"]),
            attempt_count=int(row["attempt_count"]),
        )

    def _increment(self, key: str) -> None:
        with self._counters_lock:
            self._counters[key] += 1


def _is_local_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and parsed.username is None
        and parsed.password is None
        and port is not None
    )


_dispatcher = CaptchaShadowDispatcher(
    enabled=False,
    base_url="http://127.0.0.1:8787",
    max_queue_size=1,
    timeout_seconds=2,
)


def configure_captcha_shadow(settings: Settings) -> CaptchaShadowDispatcher:
    global _dispatcher
    with _dispatcher_lock:
        if _dispatcher.status()["running"]:
            _dispatcher.stop()
        _dispatcher = CaptchaShadowDispatcher.from_settings(settings)
        return _dispatcher


def captcha_shadow_dispatcher() -> CaptchaShadowDispatcher:
    with _dispatcher_lock:
        return _dispatcher


def enqueue_shadow_prediction(
    *,
    event_id: str,
    image_path: str,
    metadata: dict[str, Any],
) -> bool:
    event = CaptchaShadowEvent(
        endpoint="/v1/predict",
        payload={
            "event_id": event_id,
            "image_path": image_path,
            "metadata": metadata,
        },
        event_key=f"{event_id}:predict",
        sequence=1,
    )
    return captcha_shadow_dispatcher().enqueue(event)


def enqueue_shadow_external_result(
    *,
    event_id: str,
    external_answer: str,
    portal_accepted: bool | None,
    external_solve_ms: float | None = None,
    final_result: bool = False,
) -> bool:
    normalized_answer = external_answer.strip().upper()
    if not CAPTCHA_ANSWER_PATTERN.fullmatch(normalized_answer):
        logger.warning(
            "captcha_shadow_invalid_external_answer event_id=%s",
            event_id,
        )
        return False
    payload: dict[str, Any] = {
        "event_id": event_id,
        "external_answer": normalized_answer,
        "portal_accepted": portal_accepted,
    }
    if external_solve_ms is not None:
        payload["external_solve_ms"] = round(max(external_solve_ms, 0.0), 3)
    event = CaptchaShadowEvent(
        endpoint="/v1/results/external",
        payload=payload,
        event_key=f"{event_id}:external:{'final' if final_result else 'initial'}",
        sequence=3 if final_result else 2,
    )
    return captcha_shadow_dispatcher().enqueue(event)
