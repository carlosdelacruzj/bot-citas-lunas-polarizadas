from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import replace
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.domain import RunReport
from appointment_bot.main import run_with_report
from appointment_bot.services.credential_cipher import CredentialDecryptionError
from appointment_bot.services.database_models import ServiceOrderCandidate, ServiceOrderRuntime
from appointment_bot.services.notifier import notify_deferred_queue_summary
from appointment_bot.services.order_runtime import (
    OrderReportOutcome,
    classify_order_report,
    order_done_status_from_report,
)
from appointment_bot.services.order_selection import (
    ReservationConstraints,
    appointment_filter_from_constraints,
)
from appointment_bot.services.order_transitions import (
    order_can_submit,
    reconcile_pending_submission,
)
from appointment_bot.services.postgres_database import (
    claim_service_order,
    clear_order_submission_state,
    create_reservation_attempt,
    get_claimed_service_order_runtime,
    get_reservation_constraints_for_order,
    list_active_orders,
    list_observer_orders,
    mark_order_done,
    mark_order_submission_intent,
    mark_order_submission_pending,
    mark_reservation_attempt_pending,
    order_backoff_seconds,
    order_reservation_pending,
    record_invalid_credential_failure,
    record_order_check,
    release_service_order_claim,
    renew_service_order_claim,
    resolve_reservation_attempt,
    set_order_paused,
    update_order_state,
)
from appointment_bot.services.run_reporting import settings_for_order

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
    minimum_hour, minimum_date, allowed_weekdays = get_reservation_constraints_for_order(
        order_id,
        settings=settings,
    )
    return appointment_filter_from_constraints(
        ReservationConstraints(
            minimum_hour=minimum_hour,
            minimum_date=minimum_date,
            allowed_weekdays=allowed_weekdays,
        )
    )


def run_rapid_queue_with_settings(
    settings: Settings,
    *,
    initial_confirmed_reservations: int = 0,
    cancel_event: threading.Event | None = None,
    on_order_start: Callable[[ServiceOrderCandidate | ServiceOrderRuntime], None] | None = None,
    on_check: Callable[..., None] | None = None,
    skip_order_ids: set[str] | None = None,
    stop_on_available_without_reserve: bool = True,
) -> RunReport:
    checked_orders = 0
    confirmed_reservations = initial_confirmed_reservations
    uncertain_reservations = 0
    failed_orders = 0
    results: list[dict[str, str]] = []
    deferred_reports: list[RunReport] = []
    lease_owner = f"queue-{uuid4().hex}"
    with ExitStack() as claims:
        # La consulta ya excluye ordenes terminadas; por eso la cola
        # empieza siempre en la orden pendiente de mayor prioridad.
        orders = [
            order
            for order in list_active_orders(settings)
            if order.order_id not in (skip_order_ids or set())
        ]
        if not orders:
            return RunReport(
                status="completed",
                message="No quedan ordenes pendientes para la cola rapida.",
                exit_code=0,
                details={
                    "checked_orders": 0,
                    "confirmed_reservations": 0,
                    "uncertain_reservations": 0,
                    "failed_orders": 0,
                    "results": [],
                },
            )

        logger.info("Starting order queue with %s active orders", len(orders))
        for index, order in enumerate(orders):
            has_more_orders = index < len(orders) - 1
            if cancel_event is not None and cancel_event.is_set():
                return RunReport(
                    status="paused",
                    message="La cola rapida fue interrumpida por una pausa.",
                    exit_code=0,
                    details={
                        "checked_orders": checked_orders,
                        "confirmed_reservations": (
                            confirmed_reservations - initial_confirmed_reservations
                        ),
                        "uncertain_reservations": uncertain_reservations,
                        "failed_orders": failed_orders,
                        "results": results,
                    },
                )
            # El valor 0 significa todos los pendientes; un valor positivo
            # conserva un limite opcional de reservas confirmadas por ejecucion.
            if _reservation_limit_reached(settings, confirmed_reservations):
                logger.info(
                    "Queue reservation limit reached: %s",
                    settings.queue_max_reservations_per_run,
                )
                break

            if not claim_service_order(
                order.order_id,
                owner_token=lease_owner,
                lease_seconds=SERVICE_ORDER_LEASE_SECONDS,
                settings=settings,
            ):
                logger.info(
                    "Skipping order %s because another worker owns its lease",
                    order.order_id,
                )
                continue
            claims.callback(
                release_service_order_claim,
                order.order_id,
                owner_token=lease_owner,
                settings=settings,
            )
            try:
                checked_orders += 1
                if on_order_start is not None:
                    on_order_start(order)
                report = run_service_order(
                    settings,
                    order,
                    lease_owner=lease_owner,
                    rapid_mode=True,
                    cancel_event=cancel_event,
                    on_check=on_check,
                )
            finally:
                # Execute and discard the current claim callback before moving
                # to the next order. ExitStack remains the exception fallback.
                claims.pop_all().close()
            results.append(
                {
                    "order_id": order.order_id,
                    "mode": "rapid",
                    "status": report.status,
                    "message": report.message,
                }
            )
            if report.status in {"available", "partial", "registered", "reservation_unconfirmed"}:
                deferred_reports.append(report)
            _update_state_from_report(settings, order, report)
            outcome = classify_order_report(report)
            if outcome is OrderReportOutcome.BLOCKED:
                logger.info(
                    "Skipping order %s temporarily because the available appointment "
                    "does not match order rules.",
                    order.order_id,
                )
                if has_more_orders:
                    _delay_between_orders(settings, cancel_event=cancel_event)
                continue
            if report.exit_code != 0 or report.status == "error":
                failed_orders += 1

            if bool((report.details or {}).get("credential_error")):
                logger.error(
                    "Order %s was paused because its credential could not be decrypted",
                    order.order_id,
                )
                if has_more_orders:
                    _delay_between_orders(settings, cancel_event=cancel_event)
                continue

            if outcome is OrderReportOutcome.TERMINAL_STAGE:
                # Estados terminales de la etapa y registered excluyen al
                # orden de ejecuciones futuras.
                mark_order_done(
                    order.order_id,
                    status=order_done_status_from_report(report),
                    settings=settings,
                )
                logger.info("Order marked as done: %s", order.order_id)
                if has_more_orders:
                    _delay_between_orders(settings, cancel_event=cancel_event)
                continue

            if outcome is OrderReportOutcome.REGISTERED:
                confirmed_reservations += 1
                mark_order_done(order.order_id, settings=settings)
                logger.info("Reservation confirmed for order: %s", order.order_id)
                if has_more_orders and not _reservation_limit_reached(
                    settings, confirmed_reservations
                ):
                    _delay_between_orders(settings, cancel_event=cancel_event)
                continue

            if outcome is OrderReportOutcome.RESERVATION_UNCONFIRMED:
                uncertain_reservations += 1
                update_order_state(
                    order.order_id,
                    status=report.status,
                    message=report.message,
                    exit_code=report.exit_code,
                    backoff_seconds=settings.error_backoff_seconds,
                    settings=settings,
                )
                logger.warning(
                    "Stopping queue after an unconfirmed reservation attempt: %s",
                    order.order_id,
                )
                break

            if report.status in {"error", "unknown"} or report.exit_code != 0:
                # Un fallo tecnico o ambiguo detiene la cola para no
                # saltar la orden prioritaria ni repetir el problema en otras cuentas.
                if report.status == "unknown":
                    failed_orders += 1
                    update_order_state(
                        order.order_id,
                        status=report.status,
                        message=report.message,
                        exit_code=1,
                        backoff_seconds=(None),
                        settings=settings,
                    )
                logger.warning(
                    "Stopping queue after terminal order result %s: %s",
                    report.status,
                    order.order_id,
                )
                break

            if report.status == "skipped":
                logger.info("Skipping order %s because it is in backoff", order.order_id)
                continue

            if (
                report.status == "available"
                and not settings.auto_reserve
                and stop_on_available_without_reserve
            ):
                logger.info(
                    "Stopping queue after availability alert with AUTO_RESERVE=false: %s",
                    order.order_id,
                )
                break

            if report.status in {"unavailable", "partial", "available", "completed"}:
                logger.info(
                    "Continuing queue after routine result for order %s",
                    order.order_id,
                )
                if has_more_orders:
                    _delay_between_orders(settings, cancel_event=cancel_event)
                continue

    queue_has_errors = bool(failed_orders or uncertain_reservations)
    queue_status = "error" if queue_has_errors else "completed"
    exit_code = 1 if queue_has_errors else 0
    run_confirmed_reservations = confirmed_reservations - initial_confirmed_reservations
    message = (
        f"Cola finalizada con {failed_orders} orden(es) con error y "
        f"{uncertain_reservations} reserva(s) sin confirmar. "
        f"Reservas confirmadas: {run_confirmed_reservations}. "
        f"Ordenes revisadas: {checked_orders}."
        if queue_has_errors
        else (
            f"Cola finalizada. Reservas confirmadas: {run_confirmed_reservations}. "
            f"Ordenes revisadas: {checked_orders}."
        )
    )
    report = RunReport(
        status=queue_status,
        message=message,
        exit_code=exit_code,
        details={
            "checked_orders": checked_orders,
            "confirmed_reservations": run_confirmed_reservations,
            "uncertain_reservations": uncertain_reservations,
            "failed_orders": failed_orders,
            "results": results,
        },
    )
    notify_deferred_queue_summary(report, settings, deferred_reports)
    return report


def run_service_order(
    settings: Settings,
    order: ServiceOrderCandidate | ServiceOrderRuntime,
    *,
    lease_owner: str,
    rapid_mode: bool = False,
    observer_mode: bool = False,
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
        )
    elif observer_mode:
        order_settings = replace(
            order_settings,
            auto_reserve=settings.auto_reserve,
            monitor_window_seconds=settings.observer_session_seconds,
            monitor_max_attempts=settings.observer_max_attempts,
            monitor_interval_min_seconds=settings.observer_interval_min_seconds,
            monitor_interval_max_seconds=settings.observer_interval_max_seconds,
        )

    attempt_id = f"attempt-{uuid4().hex}"
    attempt_created = False

    def handle_check(result, *args) -> None:
        heartbeat.ensure_owned()
        record_order_check(
            order.order_id,
            status=str(result.status),
            settings=settings,
        )
        if on_check is not None:
            details = dict(result.details or {})
            details.setdefault("orden", order.order_id)
            details.setdefault("cliente", order.notification_name)
            details.setdefault("nombre", order.name)
            details.setdefault("cuenta", order_settings.safe_username)
            on_check(replace(result, details=details), *args)

    def on_submission_intent(details) -> None:
        nonlocal attempt_created
        create_reservation_attempt(
            attempt_id,
            order.order_id,
            details=details,
            settings=settings,
        )
        attempt_created = True
        mark_order_submission_intent(order.order_id, settings=settings)

    def on_submission_started(_details) -> None:
        mark_reservation_attempt_pending(attempt_id, settings=settings)
        mark_order_submission_pending(order.order_id, settings=settings)

    def can_solve_reservation_captcha() -> bool:
        if not observer_mode:
            return True
        higher_priority_orders = [
            candidate
            for candidate in list_observer_orders(settings)
            if candidate.priority > order.priority
        ]
        if not higher_priority_orders:
            return True
        logger.info(
            "Deferring reservation for order %s because higher priority order %s is ready",
            order.order_id,
            higher_priority_orders[0].order_id,
        )
        return False

    with _ServiceOrderLeaseHeartbeat(order.order_id, lease_owner, settings) as heartbeat:
        effective_cancel_event = _CombinedEvent(cancel_event, heartbeat.lost_event)
        report = run_with_report(
            order_settings,
            order_id=order.order_id,
            client_name=order.notification_name,
            expected_person_name=order.name,
            cancel_event=effective_cancel_event,
            on_check=handle_check,
            can_submit=lambda: (
                not heartbeat.lost_event.is_set()
                and order_can_submit(order.order_id, lease_owner, settings)
            ),
            can_solve_captcha=can_solve_reservation_captcha,
            is_allowed_appointment=_appointment_filter_for_order(
                order.order_id,
                settings,
            ),
            on_submission_intent=on_submission_intent,
            on_submission_started=on_submission_started,
            notify_mode="deferred" if rapid_mode or observer_mode else "full",
        )
        lease_lost = heartbeat.lost_event.is_set()
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
            status="reservation_unconfirmed" if attempt_created else "error",
            message="Se perdio el lease de la orden durante la ejecucion; no se repetira el envio.",
            exit_code=1,
        )
    if attempt_created:
        submission_outcome = str((report.details or {}).get("submission_outcome") or "")
        if report.status == "registered":
            attempt_status = "confirmed"
        elif submission_outcome in {"captcha_invalid", "slot_lost", "rejected"}:
            attempt_status = "rejected"
        else:
            attempt_status = "unknown"
        resolve_reservation_attempt(
            attempt_id,
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


def _update_state_from_report(
    settings: Settings,
    order: ServiceOrderRuntime,
    report: RunReport,
) -> None:
    if report.status in {"skipped", "unknown", "reservation_unconfirmed"}:
        return

    update_order_state(
        order.order_id,
        status=report.status,
        message=report.message,
        exit_code=report.exit_code,
        settings=settings,
    )


def _reservation_limit_reached(
    settings: Settings,
    confirmed_reservations: int,
) -> bool:
    limit = settings.queue_max_reservations_per_run
    return limit > 0 and confirmed_reservations >= limit


def _delay_between_orders(
    settings: Settings,
    *,
    cancel_event: threading.Event | None = None,
) -> None:
    if settings.queue_delay_max_seconds <= 0:
        return

    delay = random.randint(
        settings.queue_delay_min_seconds,
        settings.queue_delay_max_seconds,
    )
    if delay <= 0:
        return

    logger.info("Waiting %s seconds before the next queued order", delay)
    if cancel_event is not None:
        cancel_event.wait(delay)
    else:
        time.sleep(delay)
