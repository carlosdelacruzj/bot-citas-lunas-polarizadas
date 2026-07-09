from __future__ import annotations

import time
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.services.postgres_worker import (
    acquire_worker_lease,
    release_worker_lease,
    renew_worker_lease,
)

WORKER_LEASE_SECONDS = 5 * 60
WORKER_LEASE_RENEW_INTERVAL_SECONDS = 60
LEASE_UNAVAILABLE_REASON = "lease_unavailable"


class WorkerLease:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.owner_token: str | None = None
        self._renewed_at: float | None = None
        self.acquired = False

    def acquire(self) -> bool:
        self.owner_token = uuid4().hex
        if not acquire_worker_lease(
            self.owner_token,
            lease_seconds=WORKER_LEASE_SECONDS,
            settings=self.settings,
        ):
            self.owner_token = None
            return False
        self.acquired = True
        self._renewed_at = time.monotonic()
        return True

    def renew_if_due(self, *, force: bool = False) -> None:
        owner_token = self.required_owner_token()
        now = time.monotonic()
        if (
            not force
            and self._renewed_at is not None
            and now - self._renewed_at < WORKER_LEASE_RENEW_INTERVAL_SECONDS
        ):
            return
        if not renew_worker_lease(
            owner_token,
            lease_seconds=WORKER_LEASE_SECONDS,
            settings=self.settings,
        ):
            raise RuntimeError("The continuous worker lease was lost.")
        self._renewed_at = now

    def release(self) -> None:
        if self.acquired and self.owner_token is not None:
            release_worker_lease(self.owner_token, settings=self.settings)
        self.acquired = False
        self.owner_token = None
        self._renewed_at = None

    def required_owner_token(self) -> str:
        if self.owner_token is None:
            raise RuntimeError("Continuous worker does not have an owner token.")
        return self.owner_token
