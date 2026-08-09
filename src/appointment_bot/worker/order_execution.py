from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.core.models import RunReport, ServiceOrderCandidate, ServiceOrderRuntime
from appointment_bot.core.rules import (
    ReservationConstraints,
    appointment_filter_from_constraints,
)
from appointment_bot.db.orders import (
    clear_order_submission_state,
    get_claimed_service_order_runtime,
    get_reservation_constraints_for_order,
    mark_order_submission_intent,
    mark_order_submission_pending,
    order_backoff_seconds,
    order_reservation_pending,
    record_invalid_credential_failure,
    renew_service_order_claim,
    set_order_paused,
    update_order_state,
)
from appointment_bot.db.reservations import (
    create_reservation_attempt,
    mark_reservation_attempt_pending,
    resolve_reservation_attempt,
)
from appointment_bot.db.runs import record_order_check
from appointment_bot.reports.run_reporting import settings_for_order
from appointment_bot.reservation_engine.runner import run_with_report
from appointment_bot.services.credential_cipher import CredentialDecryptionError
from appointment_bot.services.order_transitions import (
    order_can_submit,
    reconcile_pending_submission,
)

logger = logging.getLogger(__name__)

SERVICE_ORDER_LEASE_SECONDS = 15 * 60
SERVICE_ORDER_LEASE_RENEW_INTERVAL_SECONDS = 60


class _CombinedEvent:
    def __init__(self, *events: threading.Event | None) -> None:
        self._events = tuple(event for event in events if event is not None)

    def is_set(self) -> bool:
        return any(event.is_set() for event in self._events)

    def wait(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while not self.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.2, remaining))
        return True


class _ServiceOrderLeaseHeartbeat:
    def __init__(self, order_id: str, owner_token: str, settings: Settings) -> None:
        self.order_id = order_id
        self.owner_token = owner_token
        self.settings = settings
        self.lost_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"lease-heartbeat-{order_id}",
            daemon=True,
        )

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_args) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def ensure_owned(self) -> None:
        if self.lost_event.is_set():
            raise RuntimeError("The service order lease was lost during execution.")

    def _run(self) -> None:
        while not self._stop_event.wait(SERVICE_ORDER_LEASE_RENEW_INTERVAL_SECONDS):
            try:
                renewed = renew_service_order_claim(
                    self.order_id,
                    owner_token=self.owner_token,
                    lease_seconds=SERVICE_ORDER_LEASE_SECONDS,
                    settings=self.settings,
                )
            except Exception:
                logger.exception("Service order lease heartbeat failed: %s", self.order_id)
                renewed = False
            if not renewed:
                self.lost_event.set()
                return


def _appointment_filter_for_order(
    order_id: str,
    settings: Settings,
) -> Callable[[str, str], bool] | None:
    values = get_reservation_constraints_for_order(order_id, settings=settings)
    minimum_date, maximum_date, allowed_weekdays, excluded_date_ranges = values
    return appointment_filter_from_constraints(
        ReservationConstraints(
            minimum_date=minimum_date,
            maximum_date=maximum_date,
            allowed_weekdays=allowed_weekdays,
            excluded_date_ranges=excluded_date_ranges,
        )
    )


def run_service_order(
    settings: Settings,
    order: ServiceOrderCandidate | ServiceOrderRuntime,
    *,
    lease_owner: str,
    rapid_mode: bool = False,
    observer_mode: bool = False,
    burst_mode: bool = False,
    cancel_event: threading.Event | None = None,
    on_check: Callable[..., None] | None = None,
) -> RunReport:
    logger.info("Starting queued appointment check for order %s", order.order_id)
    try:
        current_order = get_claimed_service_order_runtime(
            order.order_id,
            owner_token=lease_owner,
            settings=settings,
        )
    except CredentialDecryptionError:
        logger.exception("Could not decrypt credentials for order %s", order.order_id)
        set_order_paused(order.order_id, True, settings=settings)
        update_order_state(
            order.order_id,
            status="error",
            message="Las credenciales cifradas de la orden no se pudieron leer.",
            exit_code=1,
            settings=settings,
        )
        return RunReport(
            status="error",
            message="Las credenciales cifradas de la orden no se pudieron leer; se pauso la orden.",
            exit_code=1,
            order_id=order.order_id,
            details={"credential_error": True},
        )
    if current_order is None:
        return RunReport(
            status="skipped",
            message="La orden dejo de estar activa o se perdio su lease antes de iniciar.",
            exit_code=0,
            order_id=order.order_id,
        )

    backoff_seconds = order_backoff_seconds(order.order_id, settings=settings)
    if backoff_seconds > 0:
        return RunReport(
            status="skipped",
            message=(
                f"Revision omitida por backoff de la orden. Faltan {backoff_seconds} segundos."
            ),
            exit_code=0,
            order_id=order.order_id,
        )

    order = current_order
    order_settings = settings_for_order(
        settings,
        username=order.username,
        password=order.password,
        document_type=order.document_type,
    )
    pending_submission = order_reservation_pending(
        order.order_id,
        settings=settings,
    )
    if pending_submission:
        order_settings = replace(order_settings, auto_reserve=False)
    if rapid_mode:
        order_settings = replace(
            order_settings,
            monitor_window_seconds=0,
            monitor_max_attempts=1,
            reservation_captcha_sample_limit=1,
            reservation_captcha_runtime_control_enabled=False,
        )
    elif burst_mode:
        order_settings = replace(
            order_settings,
            auto_reserve=settings.auto_reserve,
            monitor_window_seconds=settings.opportunity_burst_session_seconds,
            monitor_max_attempts=settings.opportunity_burst_attempts,
            monitor_interval_min_seconds=(
                settings.observer_site_toggle_interval_min_seconds
            ),
            monitor_interval_max_seconds=(
                settings.observer_site_toggle_interval_max_seconds
            ),
            monitor_site_toggle_enabled=True,
            monitor_reload_probe_after_attempt=(
                settings.opportunity_burst_reload_probe_after_attempt
            ),
            reservation_captcha_sample_limit=1,
            reservation_captcha_runtime_control_enabled=False,
        )
    elif observer_mode:
        site_toggle_enabled = settings.observer_site_toggle_enabled
        order_settings = replace(
            order_settings,
            auto_reserve=settings.auto_reserve,
            monitor_window_seconds=settings.observer_session_seconds,
            monitor_max_attempts=(
                settings.observer_site_toggle_attempts
                if site_toggle_enabled
                else settings.observer_max_attempts
            ),
            monitor_interval_min_seconds=(
                settings.observer_site_toggle_interval_min_seconds
                if site_toggle_enabled
                else settings.observer_interval_min_seconds
            ),
            monitor_interval_max_seconds=(
                settings.observer_site_toggle_interval_max_seconds
                if site_toggle_enabled
                else settings.observer_interval_max_seconds
            ),
            monitor_site_toggle_enabled=site_toggle_enabled,
            monitor_reload_probe_after_attempt=settings.observer_reload_probe_after_attempt,
        )

    active_attempt_id: str | None = None

    def with_order_details(result):
        details = dict(result.details or {})
        details.setdefault("orden", order.order_id)
        details.setdefault("cliente", order.notification_name)
        details.setdefault("nombre", order.name)
        details.setdefault("cuenta", order_settings.safe_username)
        if order.contact_name:
            details.setdefault("contact_name", order.contact_name)
        if order.contact_whatsapp:
            details.setdefault("contact_whatsapp", order.contact_whatsapp)
        elif order.contact_whatsapp_username:
            details.setdefault(
                "contact_whatsapp_username", order.contact_whatsapp_username
            )
        if order.contact_source:
            details.setdefault("contact_source", order.contact_source)
        if order.program_expediente:
            details.setdefault("program_expediente", order.program_expediente)
        if order.program_plate:
            details.setdefault("program_plate", order.program_plate)
        return replace(result, details=details)

    def handle_check(result, *args) -> None:
        heartbeat.ensure_owned()
        record_order_check(
            order.order_id,
            status=str(result.status),
            settings=settings,
        )
        if on_check is not None:
            on_check(with_order_details(result), *args)

    def on_submission_intent(details) -> None:
        nonlocal active_attempt_id
        if active_attempt_id is None:
            active_attempt_id = f"attempt-{uuid4().hex}"
        create_reservation_attempt(
            active_attempt_id,
            order.order_id,
            details=details,
            settings=settings,
        )
        mark_order_submission_intent(order.order_id, settings=settings)

    def on_submission_started(_details) -> None:
        if active_attempt_id is None:
            raise RuntimeError("Reservation submission started without a durable intent.")
        mark_reservation_attempt_pending(active_attempt_id, settings=settings)
        mark_order_submission_pending(order.order_id, settings=settings)

    def on_submission_resolved(
        outcome: str,
        resolved_run_id: str | None,
        evidence_path: str | None,
    ) -> None:
        nonlocal active_attempt_id
        if outcome != "slot_lost":
            raise ValueError(f"Unsupported intermediate submission outcome: {outcome}")
        if active_attempt_id is None:
            raise RuntimeError("Reservation submission resolved without an active attempt.")
        resolve_reservation_attempt(
            active_attempt_id,
            "rejected",
            run_id=resolved_run_id,
            evidence_path=evidence_path,
            settings=settings,
        )
        clear_order_submission_state(order.order_id, settings=settings)
        active_attempt_id = None

    with _ServiceOrderLeaseHeartbeat(order.order_id, lease_owner, settings) as heartbeat:
        effective_cancel_event = _CombinedEvent(cancel_event, heartbeat.lost_event)
        report = run_with_report(
            order_settings,
            order_id=order.order_id,
            client_name=order.notification_name,
            expected_person_name=order.name,
            program_expediente=order.program_expediente,
            program_plate=order.program_plate,
            cancel_event=effective_cancel_event,
            on_check=handle_check,
            can_submit=lambda: (
                not heartbeat.lost_event.is_set()
                and order_can_submit(order.order_id, lease_owner, settings)
            ),
            is_allowed_appointment=_appointment_filter_for_order(
                order.order_id,
                settings,
            ),
            on_submission_intent=on_submission_intent,
            on_submission_started=on_submission_started,
            on_submission_resolved=on_submission_resolved,
            notify_mode=(
                "deferred" if rapid_mode or observer_mode or burst_mode else "full"
            ),
        )
        lease_lost = heartbeat.lost_event.is_set()
    report = with_order_details(report)
    if str((report.details or {}).get("error_type") or "") == "InvalidPortalCredentials":
        failures, paused = record_invalid_credential_failure(
            order.order_id,
            settings=settings,
        )
        details = dict(report.details or {})
        details.update(
            {
                "credential_error": True,
                "credential_failure_count": failures,
                "credential_paused": paused,
            }
        )
        report = replace(
            report,
            message=(
                "El portal rechazo la clave por segunda vez; la orden fue pausada."
                if paused
                else "El portal rechazo la clave; queda un intento antes de pausar la orden."
            ),
            details=details,
        )
    if lease_lost and report.status != "registered":
        report = replace(
            report,
            status="reservation_unconfirmed" if active_attempt_id is not None else "error",
            message="Se perdio el lease de la orden durante la ejecucion; no se repetira el envio.",
            exit_code=1,
        )
    if active_attempt_id is not None:
        submission_outcome = str((report.details or {}).get("submission_outcome") or "")
        if report.status == "registered":
            attempt_status = "confirmed"
        elif submission_outcome in {"captcha_invalid", "slot_lost", "rejected"}:
            attempt_status = "rejected"
        else:
            attempt_status = "unknown"
        resolve_reservation_attempt(
            active_attempt_id,
            attempt_status,
            run_id=report.run_id,
            evidence_path=report.screenshot_path,
            settings=settings,
        )
        if attempt_status in {"confirmed", "rejected"}:
            clear_order_submission_state(order.order_id, settings=settings)
    if pending_submission:
        if reconcile_pending_submission(order.order_id, report, settings):
            return report
        return replace(
            report,
            status="reservation_unconfirmed",
            message=(
                "Existe un envio de reserva pendiente. Se verifico el portal sin "
                "intentar una nueva reserva."
            ),
            exit_code=1,
        )
    return report
