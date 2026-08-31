from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError

from appointment_bot.browser.ownership import BrowserOwnershipLease
from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings
from appointment_bot.core.models import ServiceOrderRuntime
from appointment_bot.manual_session.diagnostics import ManualDiagnosticRecorder
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
    mode: str
    order_status: str
    status: str
    status_message: str | None
    started_at: str
    updated_at: str
    close_requested: threading.Event
    browser_lease: BrowserOwnershipLease
    thread: threading.Thread | None
    diagnostic_report_path: str | None
    diagnostic_event_count: int
    diagnostic_submission_seen: bool
    diagnostic_honeypot_blocked: bool

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "order_id": self.order_id,
            "username": self.username,
            "mode": self.mode,
            "order_status": self.order_status,
            "status": self.status,
            "status_message": self.status_message,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "close_requested": self.close_requested.is_set(),
            "diagnostic_report_path": self.diagnostic_report_path,
            "diagnostic_event_count": self.diagnostic_event_count,
            "diagnostic_submission_seen": self.diagnostic_submission_seen,
            "diagnostic_honeypot_blocked": self.diagnostic_honeypot_blocked,
        }


_ACTIVE_SESSION_LOCK = threading.Lock()
_ACTIVE_SESSIONS: dict[str, ManualSessionHandle] = {}
MANUAL_SESSION_CLOSE_GRACE_SECONDS = 8


def open_manual_session_for_order(
    settings: Settings,
    order: ServiceOrderRuntime,
    *,
    mode: str = "appointment",
) -> str:
    session_id = f"manual-session-{uuid4().hex[:12]}"
    session_settings = settings_for_order(
        settings,
        username=order.username,
        password=order.password,
        document_type=order.document_type,
    )
    browser_lease = BrowserOwnershipLease.acquire(
        settings,
        order.order_id,
        owner_token=session_id,
        purpose="manual",
    )
    now = datetime.now(UTC).isoformat(timespec="seconds")
    handle = ManualSessionHandle(
        session_id=session_id,
        order_id=order.order_id,
        username=session_settings.safe_username,
        mode=mode,
        order_status=order.status,
        status="opening",
        status_message=None,
        started_at=now,
        updated_at=now,
        close_requested=threading.Event(),
        browser_lease=browser_lease,
        thread=None,
        diagnostic_report_path=None,
        diagnostic_event_count=0,
        diagnostic_submission_seen=False,
        diagnostic_honeypot_blocked=False,
    )
    try:
        with _ACTIVE_SESSION_LOCK:
            _ACTIVE_SESSIONS[session_id] = handle
            active_count = len(_ACTIVE_SESSIONS)
    except Exception:
        browser_lease.close()
        raise
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
    handle.thread = thread
    try:
        thread.start()
    except Exception:
        _clear_active_session(session_id)
        browser_lease.close()
        raise
    return session_id


def close_manual_session(session_id: str) -> bool:
    with _ACTIVE_SESSION_LOCK:
        handle = _ACTIVE_SESSIONS.get(session_id)
        if handle is not None:
            if handle.status != "close_timeout":
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


def list_manual_sessions() -> list[dict[str, Any]]:
    with _ACTIVE_SESSION_LOCK:
        return [handle.summary() for handle in _ACTIVE_SESSIONS.values()]


def blocking_manual_sessions() -> list[dict[str, Any]]:
    with _ACTIVE_SESSION_LOCK:
        return [
            handle.summary()
            for handle in _ACTIVE_SESSIONS.values()
            if handle.status in {"opening", "active", "closing", "close_timeout"}
        ]


def _run_manual_session(
    settings: Settings,
    order: ServiceOrderRuntime,
    handle: ManualSessionHandle,
) -> None:
    session_id = handle.session_id
    diagnostic = (
        ManualDiagnosticRecorder(settings, session_id, order.order_id)
        if handle.mode == "diagnostic"
        else None
    )
    if diagnostic is not None:
        _sync_diagnostic_status(session_id, diagnostic)
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
    diagnostic_error: str | None = None
    try:
        with open_page(
            session_settings,
            headless=False,
            block_heavy_assets=False,
        ) as page:
            if diagnostic is not None:
                diagnostic.attach(page)
            try:
                _prepare_manual_session(
                    page,
                    session_settings,
                    order,
                    session_id,
                    mode=handle.mode,
                )
                if diagnostic is not None:
                    diagnostic.record("portal_ready", path="/lunasoscurecidas/Seguimiento.aspx")
            except Exception as exc:
                if diagnostic is not None:
                    diagnostic.record("preparation_error", error=type(exc).__name__)
                _set_session_status(
                    session_id,
                    "active",
                    "No se pudo preparar la vista solicitada; el navegador sigue abierto.",
                )
                logger.exception(
                    "Manual session preparation failed; keeping browser open: "
                    "session_id=%s order_id=%s",
                    session_id,
                    order.order_id,
                )
            _wait_until_manual_session_closed(page, handle, diagnostic=diagnostic)
    except Exception as exc:
        diagnostic_error = type(exc).__name__
        logger.exception(
            "Manual session failed: session_id=%s order_id=%s",
            session_id,
            order.order_id,
        )
    finally:
        if diagnostic is not None:
            diagnostic.finish(
                state="error" if diagnostic_error else "closed",
                error=diagnostic_error,
            )
            _sync_diagnostic_status(session_id, diagnostic)
        _clear_active_session(session_id)
        logger.info(
            "Manual session closed: session_id=%s order_id=%s",
            session_id,
            order.order_id,
        )


def _wait_until_manual_session_closed(
    page,
    handle: ManualSessionHandle,
    *,
    diagnostic: ManualDiagnosticRecorder | None = None,
) -> None:
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
        if handle.browser_lease.lost:
            _set_session_status(
                handle.session_id,
                "closing",
                "La propiedad exclusiva de la cuenta se perdio; cerrando navegador.",
            )
            handle.close_requested.set()
            break
        try:
            if page.is_closed() or not page.context.pages:
                break
            if diagnostic is not None:
                diagnostic.poll(page)
                _sync_diagnostic_status(handle.session_id, diagnostic)
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
    *,
    mode: str,
) -> None:
    login(page, settings)
    if mode in {"portal", "diagnostic"}:
        _set_session_status(
            session_id,
            "active",
            (
                "Medicion sanitizada activa desde el inicio del portal."
                if mode == "diagnostic"
                else "Portal abierto en modo de consulta manual."
            ),
        )
        logger.info(
            "Manual portal session ready: session_id=%s order_id=%s order_status=%s",
            session_id,
            order.order_id,
            order.status,
        )
        return
    click_program_action(
        page,
        program_expediente=order.program_expediente,
        program_plate=order.program_plate,
    )
    open_appointment_panel(page)
    select_available_site(page, required_site=settings.observer_required_site)
    _set_session_status(
        session_id,
        "active",
        "Panel de citas abierto para revisión manual.",
    )
    logger.info(
        "Manual session ready at appointment panel: session_id=%s order_id=%s site=%s",
        session_id,
        order.order_id,
        settings.observer_required_site,
    )


def _set_session_status(
    session_id: str,
    status: str,
    status_message: str | None = None,
) -> None:
    with _ACTIVE_SESSION_LOCK:
        handle = _ACTIVE_SESSIONS.get(session_id)
        if handle is not None:
            handle.status = status
            handle.status_message = status_message
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


def _sync_diagnostic_status(
    session_id: str,
    diagnostic: ManualDiagnosticRecorder,
) -> None:
    with _ACTIVE_SESSION_LOCK:
        handle = _ACTIVE_SESSIONS.get(session_id)
        if handle is None:
            return
        handle.diagnostic_report_path = str(diagnostic.report_path)
        handle.diagnostic_event_count = diagnostic.event_count
        handle.diagnostic_submission_seen = diagnostic.submission_seen
        handle.diagnostic_honeypot_blocked = diagnostic.honeypot_blocked
        handle.updated_at = datetime.now(UTC).isoformat(timespec="seconds")


def _expire_closing_session(session_id: str, expected_handle: ManualSessionHandle) -> None:
    with _ACTIVE_SESSION_LOCK:
        current = _ACTIVE_SESSIONS.get(session_id)
        if current is not expected_handle or not current.close_requested.is_set():
            return
        current.status = "close_timeout"
        current.status_message = (
            "El navegador no termino dentro del tiempo esperado; sigue bloqueando reinicios."
        )
        current.updated_at = datetime.now(UTC).isoformat(timespec="seconds")
    logger.warning(
        "Manual session still active after close timeout: "
        "session_id=%s order_id=%s grace_seconds=%s",
        session_id,
        expected_handle.order_id,
        MANUAL_SESSION_CLOSE_GRACE_SECONDS,
    )
