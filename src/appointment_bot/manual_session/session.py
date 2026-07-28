from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings
from appointment_bot.core.models import ServiceOrderRuntime
from appointment_bot.reports.run_reporting import settings_for_order
from appointment_bot.reservation_engine.appointments import (
    open_appointment_panel,
    select_available_site,
)
from appointment_bot.reservation_engine.login import login
from appointment_bot.reservation_engine.programs import click_program_action

logger = logging.getLogger(__name__)


@dataclass
class ManualSessionHandle:
    session_id: str
    order_id: str
    username: str
    status: str
    started_at: str
    updated_at: str
    close_requested: threading.Event

    def summary(self) -> dict[str, str | bool]:
        return {
            "session_id": self.session_id,
            "order_id": self.order_id,
            "username": self.username,
            "status": self.status,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "close_requested": self.close_requested.is_set(),
        }


_ACTIVE_SESSION_LOCK = threading.Lock()
_ACTIVE_SESSIONS: dict[str, ManualSessionHandle] = {}
MANUAL_SESSION_CLOSE_GRACE_SECONDS = 8


def open_manual_session_for_order(
    settings: Settings,
    order: ServiceOrderRuntime,
) -> str:
    session_id = f"manual-session-{uuid4().hex[:12]}"
    session_settings = settings_for_order(
        settings,
        username=order.username,
        password=order.password,
        document_type=order.document_type,
    )
    now = datetime.now(UTC).isoformat(timespec="seconds")
    handle = ManualSessionHandle(
        session_id=session_id,
        order_id=order.order_id,
        username=session_settings.safe_username,
        status="opening",
        started_at=now,
        updated_at=now,
        close_requested=threading.Event(),
    )
    with _ACTIVE_SESSION_LOCK:
        _ACTIVE_SESSIONS[session_id] = handle
        active_count = len(_ACTIVE_SESSIONS)
    logger.info(
        "Manual session registered: session_id=%s order_id=%s active_sessions=%s",
        session_id,
        order.order_id,
        active_count,
    )

    thread = threading.Thread(
        target=_run_manual_session,
        name=session_id,
        args=(settings, order, handle),
        daemon=True,
    )
    thread.start()
    return session_id


def close_manual_session(session_id: str) -> bool:
    with _ACTIVE_SESSION_LOCK:
        handle = _ACTIVE_SESSIONS.get(session_id)
        if handle is not None:
            handle.status = "closing"
            handle.updated_at = datetime.now(UTC).isoformat(timespec="seconds")
    if handle is None:
        return False
    handle.close_requested.set()
    cleanup_timer = threading.Timer(
        MANUAL_SESSION_CLOSE_GRACE_SECONDS,
        _expire_closing_session,
        args=(session_id, handle),
    )
    cleanup_timer.daemon = True
    cleanup_timer.start()
    logger.info(
        "Manual session close requested: session_id=%s order_id=%s",
        handle.session_id,
        handle.order_id,
    )
    return True


def list_manual_sessions() -> list[dict[str, str | bool]]:
    with _ACTIVE_SESSION_LOCK:
        return [handle.summary() for handle in _ACTIVE_SESSIONS.values()]


def _run_manual_session(
    settings: Settings,
    order: ServiceOrderRuntime,
    handle: ManualSessionHandle,
) -> None:
    session_id = handle.session_id
    session_settings = replace(
        settings_for_order(
            settings,
            username=order.username,
            password=order.password,
            document_type=order.document_type,
        ),
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
            try:
                _prepare_manual_session(page, session_settings, order, session_id)
            except Exception:
                logger.exception(
                    "Manual session preparation failed; keeping browser open: "
                    "session_id=%s order_id=%s",
                    session_id,
                    order.order_id,
                )
            _wait_until_manual_session_closed(page, handle)
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


def _wait_until_manual_session_closed(page, handle: ManualSessionHandle) -> None:
    closed_event = threading.Event()

    def mark_closed(*_args) -> None:
        closed_event.set()

    page.on("close", mark_closed)
    try:
        page.context.on("close", mark_closed)
    except Exception:
        logger.debug(
            "Manual session context close event is not available: session_id=%s",
            handle.session_id,
        )

    while not closed_event.wait(1):
        if handle.close_requested.is_set():
            break
        try:
            if page.is_closed() or not page.context.pages:
                break
        except PlaywrightError:
            break
    logger.info(
        "Manual session close detected: session_id=%s order_id=%s requested=%s",
        handle.session_id,
        handle.order_id,
        handle.close_requested.is_set(),
    )


def _prepare_manual_session(
    page,
    settings: Settings,
    order: ServiceOrderRuntime,
    session_id: str,
) -> None:
    login(page, settings)
    click_program_action(
        page,
        program_expediente=order.program_expediente,
        program_plate=order.program_plate,
    )
    open_appointment_panel(page)
    select_available_site(page, required_site=settings.observer_required_site)
    _set_session_status(session_id, "ready")
    logger.info(
        "Manual session ready at appointment panel: session_id=%s order_id=%s site=%s",
        session_id,
        order.order_id,
        settings.observer_required_site,
    )


def _set_session_status(session_id: str, status: str) -> None:
    with _ACTIVE_SESSION_LOCK:
        handle = _ACTIVE_SESSIONS.get(session_id)
        if handle is not None:
            handle.status = status
            handle.updated_at = datetime.now(UTC).isoformat(timespec="seconds")


def _clear_active_session(session_id: str) -> None:
    with _ACTIVE_SESSION_LOCK:
        _ACTIVE_SESSIONS.pop(session_id, None)
        active_count = len(_ACTIVE_SESSIONS)
    logger.info(
        "Manual session unregistered: session_id=%s active_sessions=%s",
        session_id,
        active_count,
    )


def _expire_closing_session(session_id: str, expected_handle: ManualSessionHandle) -> None:
    with _ACTIVE_SESSION_LOCK:
        current = _ACTIVE_SESSIONS.get(session_id)
        if current is not expected_handle or not current.close_requested.is_set():
            return
        _ACTIVE_SESSIONS.pop(session_id, None)
    logger.warning(
        "Manual session removed after close timeout: session_id=%s order_id=%s grace_seconds=%s",
        session_id,
        expected_handle.order_id,
        MANUAL_SESSION_CLOSE_GRACE_SECONDS,
    )
