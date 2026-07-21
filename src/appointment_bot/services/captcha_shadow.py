from __future__ import annotations

import json
import logging
import queue
import re
import threading
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from appointment_bot.config import Settings

logger = logging.getLogger(__name__)
_dispatcher_lock = threading.Lock()
CAPTCHA_ANSWER_PATTERN = re.compile(r"[A-Z0-9]{5}")


@dataclass(frozen=True)
class CaptchaShadowEvent:
    endpoint: str
    payload: dict[str, Any]


class CaptchaShadowDispatcher:
    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        max_queue_size: int,
        timeout_seconds: int,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
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
        }

    @classmethod
    def from_settings(cls, settings: Settings) -> CaptchaShadowDispatcher:
        return cls(
            enabled=settings.captcha_shadow_enabled,
            base_url=settings.captcha_shadow_url,
            max_queue_size=settings.captcha_shadow_queue_size,
            timeout_seconds=settings.captcha_shadow_timeout_seconds,
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
        logger.info("CAPTCHA shadow dispatcher started: %s", self.base_url)

    def stop(self, *, timeout: float = 2.0) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=max(timeout, 0.0))
        if self._thread.is_alive():
            logger.warning("CAPTCHA shadow dispatcher did not stop before timeout")
        else:
            logger.info("CAPTCHA shadow dispatcher stopped")
            self._thread = None

    def enqueue(self, event: CaptchaShadowEvent) -> bool:
        if not self.enabled:
            return False
        try:
            self._events.put_nowait(event)
        except queue.Full:
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
        while not self._stop_event.is_set():
            try:
                event = self._events.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._send(event)
            except Exception:
                self._increment("failed")
                logger.exception(
                    "captcha_shadow_unexpected_error event_id=%s",
                    event.payload.get("event_id", "<missing>"),
                )
            finally:
                self._events.task_done()

    def _send(self, event: CaptchaShadowEvent) -> None:
        event_id = str(event.payload.get("event_id") or "<missing>")
        request = Request(
            f"{self.base_url}{event.endpoint}",
            data=json.dumps(event.payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            self._increment("failed")
            logger.warning(
                "captcha_shadow_request_failed endpoint=%s event_id=%s error=%s",
                event.endpoint,
                event_id,
                exc,
            )
            return
        self._increment("processed")
        logger.info(
            "captcha_shadow_request_completed endpoint=%s event_id=%s",
            event.endpoint,
            event_id,
        )

    def _increment(self, key: str) -> None:
        with self._counters_lock:
            self._counters[key] += 1


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
    )
    return captcha_shadow_dispatcher().enqueue(event)


def enqueue_shadow_external_result(
    *,
    event_id: str,
    external_answer: str,
    portal_accepted: bool | None,
) -> bool:
    normalized_answer = external_answer.strip().upper()
    if not CAPTCHA_ANSWER_PATTERN.fullmatch(normalized_answer):
        logger.warning(
            "captcha_shadow_invalid_external_answer event_id=%s",
            event_id,
        )
        return False
    event = CaptchaShadowEvent(
        endpoint="/v1/results/external",
        payload={
            "event_id": event_id,
            "external_answer": normalized_answer,
            "portal_accepted": portal_accepted,
        },
    )
    return captcha_shadow_dispatcher().enqueue(event)
