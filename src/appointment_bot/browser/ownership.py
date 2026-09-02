from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from appointment_bot.config import Settings
from appointment_bot.db.browser_ownership import acquire_browser_ownership
from appointment_bot.db.order_state import (
    release_service_order_claim,
    renew_service_order_claim,
)

logger = logging.getLogger(__name__)

BROWSER_OWNERSHIP_LEASE_SECONDS = 90
BROWSER_OWNERSHIP_HEARTBEAT_SECONDS = 30


@dataclass
class BrowserOwnershipLease:
    settings: Settings
    order_id: str
    owner_token: str
    purpose: str
    _stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _lost_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    @classmethod
    def acquire(
        cls,
        settings: Settings,
        order_id: str,
        *,
        owner_token: str,
        purpose: str,
        require_ready: bool = False,
    ) -> BrowserOwnershipLease:
        acquire_browser_ownership(
            order_id,
            owner_token=owner_token,
            purpose=purpose,
            lease_seconds=BROWSER_OWNERSHIP_LEASE_SECONDS,
            require_ready=require_ready,
            settings=settings,
        )
        lease = cls(settings, order_id, owner_token, purpose)
        lease._thread = threading.Thread(
            target=lease._heartbeat,
            name=f"browser-owner-{owner_token}",
            daemon=True,
        )
        lease._thread.start()
        return lease

    @property
    def lost(self) -> bool:
        return self._lost_event.is_set()

    def close(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        release_service_order_claim(
            self.order_id,
            owner_token=self.owner_token,
            settings=self.settings,
        )

    def __enter__(self) -> BrowserOwnershipLease:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _heartbeat(self) -> None:
        while not self._stop_event.wait(BROWSER_OWNERSHIP_HEARTBEAT_SECONDS):
            try:
                renewed = renew_service_order_claim(
                    self.order_id,
                    owner_token=self.owner_token,
                    lease_seconds=BROWSER_OWNERSHIP_LEASE_SECONDS,
                    settings=self.settings,
                )
            except Exception:
                logger.exception(
                    "Browser ownership heartbeat failed: order_id=%s purpose=%s",
                    self.order_id,
                    self.purpose,
                )
                renewed = False
            if not renewed:
                self._lost_event.set()
                logger.error(
                    "Browser ownership was lost: order_id=%s purpose=%s",
                    self.order_id,
                    self.purpose,
                )
                return
