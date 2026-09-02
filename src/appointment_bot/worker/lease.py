from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.db.worker_state import (
    acquire_worker_lease,
    release_worker_lease,
    renew_worker_lease,
)

logger = logging.getLogger(__name__)

WORKER_LEASE_SECONDS = 5 * 60
WORKER_LEASE_RENEW_INTERVAL_SECONDS = 60
WORKER_LEASE_RETRY_INTERVAL_SECONDS = 5
LEASE_UNAVAILABLE_REASON = "lease_unavailable"
LEASE_LOST_REASON = "lease_lost"


class WorkerLeaseLost(RuntimeError):
    pass


class WorkerLease:
    def __init__(
        self,
        settings: Settings,
        *,
        on_lost: Callable[[], None] | None = None,
        lease_seconds: float = WORKER_LEASE_SECONDS,
        renew_interval_seconds: float = WORKER_LEASE_RENEW_INTERVAL_SECONDS,
        retry_interval_seconds: float = WORKER_LEASE_RETRY_INTERVAL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.owner_token: str | None = None
        self.acquired = False
        self.lost_event = threading.Event()
        self._on_lost = on_lost
        self._lease_seconds = lease_seconds
        self._renew_interval_seconds = renew_interval_seconds
        self._retry_interval_seconds = retry_interval_seconds
        self._monotonic = monotonic
        self._lease_deadline: float | None = None
        self._stop_event = threading.Event()
        self._renew_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def lost(self) -> bool:
        return self.lost_event.is_set()

    def acquire(self) -> bool:
        if self.owner_token is not None or self._thread is not None:
            raise RuntimeError("The continuous worker lease is already active.")
        owner_token = uuid4().hex
        acquisition_started_at = self._monotonic()
        if not acquire_worker_lease(
            owner_token,
            lease_seconds=self._lease_seconds,
            settings=self.settings,
        ):
            return False
        self.owner_token = owner_token
        self.acquired = True
        self.lost_event.clear()
        self._stop_event.clear()
        self._lease_deadline = acquisition_started_at + self._lease_seconds
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name="continuous-worker-lease-heartbeat",
            daemon=True,
        )
        self._thread.start()
        return True

    def ensure_owned(self) -> None:
        deadline = self._lease_deadline
        if (
            self.owner_token is None
            or self.lost
            or deadline is None
            or self._monotonic() >= deadline
        ):
            self._mark_lost()
            raise WorkerLeaseLost("The continuous worker lease was lost.")

    def release(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(5.0, self._retry_interval_seconds + 1.0))
            if thread.is_alive():
                logger.warning("Worker lease heartbeat did not stop before release timeout")
        owner_token = self.owner_token
        if owner_token is not None:
            try:
                release_worker_lease(owner_token, settings=self.settings)
            except Exception:
                logger.exception("Could not release the continuous worker lease cleanly")
        self.acquired = False
        self.owner_token = None
        self._lease_deadline = None
        self._thread = None

    def required_owner_token(self) -> str:
        self.ensure_owned()
        assert self.owner_token is not None
        return self.owner_token

    def _heartbeat_loop(self) -> None:
        wait_seconds = self._renew_interval_seconds
        while not self._stop_event.wait(wait_seconds):
            renewed = self._renew_once()
            if self.lost:
                return
            wait_seconds = (
                self._renew_interval_seconds
                if renewed
                else self._retry_interval_seconds
            )

    def _renew_once(self) -> bool:
        with self._renew_lock:
            if self._stop_event.is_set() or self.lost:
                return False
            owner_token = self.owner_token
            if owner_token is None:
                self._mark_lost()
                return False
            renewal_started_at = self._monotonic()
            try:
                renewed = renew_worker_lease(
                    owner_token,
                    lease_seconds=self._lease_seconds,
                    settings=self.settings,
                )
            except Exception:
                logger.exception("Continuous worker lease heartbeat failed")
                deadline = self._lease_deadline
                if deadline is None or self._monotonic() >= deadline:
                    self._mark_lost()
                return False
            if self._stop_event.is_set():
                return False
            if not renewed:
                self._mark_lost()
                return False
            self._lease_deadline = renewal_started_at + self._lease_seconds
            return True

    def _mark_lost(self) -> None:
        if self.lost_event.is_set():
            return
        self.acquired = False
        self.lost_event.set()
        logger.error("Continuous worker lease ownership was lost")
        if self._on_lost is not None:
            try:
                self._on_lost()
            except Exception:
                logger.exception("Worker lease loss callback failed")


__all__ = [
    "LEASE_LOST_REASON",
    "LEASE_UNAVAILABLE_REASON",
    "WorkerLease",
    "WorkerLeaseLost",
]
