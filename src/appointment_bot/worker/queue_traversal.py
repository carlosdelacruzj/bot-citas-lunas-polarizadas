from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import ExitStack
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.db.orders import (
    claim_service_order,
    list_active_orders,
    mark_order_done,
    promote_orders_matching_reserved_slot,
    release_service_order_claim,
    update_order_state,
)
from appointment_bot.domain import RunReport
from appointment_bot.services.database_models import ServiceOrderCandidate, ServiceOrderRuntime
from appointment_bot.services.notifier import notify_deferred_queue_summary
from appointment_bot.services.order_runtime import (
    OrderReportOutcome,
    classify_order_report,
    order_done_status_from_report,
)
from appointment_bot.worker.order_execution import run_service_order
from appointment_bot.worker.queue_policy import (
    delay_between_orders as _delay_between_orders,
)
from appointment_bot.worker.queue_policy import (
    reservation_limit_reached as _reservation_limit_reached,
)
from appointment_bot.worker.queue_policy import (
    update_state_from_report as _update_state_from_report,
)

logger = logging.getLogger(__name__)

SERVICE_ORDER_LEASE_SECONDS = 15 * 60
SERVICE_ORDER_LEASE_RENEW_INTERVAL_SECONDS = 60


def run_rapid_queue_with_settings(
    settings: Settings,
    *,
    initial_confirmed_reservations: int = 0,
    cancel_event: threading.Event | None = None,
    on_order_start: Callable[[ServiceOrderCandidate | ServiceOrderRuntime], None] | None = None,
    on_check: Callable[..., None] | None = None,
    skip_order_ids: set[str] | None = None,
    follow_up_order_ids: set[str] | None = None,
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
        skipped_orders = skip_order_ids or set()
        orders = [
            order
            for order in list_active_orders(settings, include_constrained=False)
            if order.order_id not in skipped_orders
        ]
        queued_order_ids = {order.order_id for order in orders}
        for order in list_active_orders(settings, order_ids=follow_up_order_ids or set()):
            if order.order_id in skipped_orders or order.order_id in queued_order_ids:
                continue
            orders.append(order)
            queued_order_ids.add(order.order_id)
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
                promoted_orders = promote_orders_matching_reserved_slot(
                    report.details or {},
                    excluded_order_id=order.order_id,
                    settings=settings,
                )
                if promoted_orders:
                    logger.info(
                        "Promoted %s constrained order(s) after confirmed reservation %s: %s",
                        len(promoted_orders),
                        order.order_id,
                        ", ".join(candidate.order_id for candidate in promoted_orders),
                    )
                    for promoted_order in promoted_orders:
                        if (
                            promoted_order.order_id in skipped_orders
                            or promoted_order.order_id in queued_order_ids
                        ):
                            continue
                        orders.append(promoted_order)
                        queued_order_ids.add(promoted_order.order_id)
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
