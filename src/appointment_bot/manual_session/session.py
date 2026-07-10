from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings
from appointment_bot.reservation_engine.login import login
from appointment_bot.services.database_models import ServiceOrderRuntime
from appointment_bot.services.run_reporting import settings_for_order

logger = logging.getLogger(__name__)

_ACTIVE_SESSION_LOCK = threading.Lock()
_ACTIVE_SESSION_ID: str | None = None


def open_manual_session_for_order(
    settings: Settings,
    order: ServiceOrderRuntime,
) -> str:
    global _ACTIVE_SESSION_ID
    with _ACTIVE_SESSION_LOCK:
        if _ACTIVE_SESSION_ID is not None:
            raise RuntimeError("A manual session is already active in this process.")
        session_id = f"manual-session-{uuid4().hex[:12]}"
        _ACTIVE_SESSION_ID = session_id

    thread = threading.Thread(
        target=_run_manual_session,
        name=session_id,
        args=(settings, order, session_id),
        daemon=True,
    )
    thread.start()
    return session_id


def _run_manual_session(
    settings: Settings,
    order: ServiceOrderRuntime,
    session_id: str,
) -> None:
    session_settings = replace(
        settings_for_order(settings, username=order.username, password=order.password),
        headless=False,
        auto_reserve=False,
        monitor_window_seconds=0,
        telegram_notify_unavailable=False,
        artifact_prefix=session_id,
    )
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    logger.info(
        "Manual session opening: session_id=%s order_id=%s username=%s started_at=%s",
        session_id,
        order.order_id,
        session_settings.safe_username,
        started_at,
    )
    try:
        with open_page(
            session_settings,
            headless=False,
            block_heavy_assets=False,
        ) as page:
            login(page, session_settings)
            logger.info(
                "Manual session ready: session_id=%s order_id=%s",
                session_id,
                order.order_id,
            )
            while not page.is_closed():
                time.sleep(1)
    except Exception:
        logger.exception(
            "Manual session failed: session_id=%s order_id=%s",
            session_id,
            order.order_id,
        )
    finally:
        _clear_active_session(session_id)
        logger.info(
            "Manual session closed: session_id=%s order_id=%s",
            session_id,
            order.order_id,
        )


def _clear_active_session(session_id: str) -> None:
    global _ACTIVE_SESSION_ID
    with _ACTIVE_SESSION_LOCK:
        if _ACTIVE_SESSION_ID == session_id:
            _ACTIVE_SESSION_ID = None
