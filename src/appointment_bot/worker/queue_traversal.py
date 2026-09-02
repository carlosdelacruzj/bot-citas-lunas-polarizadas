from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.core.models import RunReport, ServiceOrderCandidate, ServiceOrderRuntime
from appointment_bot.db.orders import (
    claim_service_order,
    list_active_orders,
    mark_order_done,
    release_service_order_claim,
    update_order_state,
)
from appointment_bot.db.whatsapp_automation import enqueue_whatsapp_automation_job
from appointment_bot.services.notifier import notify_deferred_queue_summary
from appointment_bot.services.order_runtime import (
    OrderReportOutcome,
    classify_order_report,
    order_done_status_from_report,
)
from appointment_bot.worker.order_execution import run_service_order
from appointment_bot.worker.post_reservation_review import (
    replace_reports_with_reviewed_evidence,
    review_confirmed_orders_after_queue,
)
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


@dataclass(frozen=True)
class QueueTraversalDependencies:
    list_active_orders: Callable[..., list]
    claim_service_order: Callable[..., bool]
    release_service_order_claim: Callable[..., bool]
    update_order_state: Callable[..., Any]
    mark_order_done: Callable[..., Any]
    run_service_order: Callable[..., RunReport]
    update_state_from_report: Callable[..., Any]
    delay_between_orders: Callable[..., Any]


DEFAULT_QUEUE_TRAVERSAL_DEPENDENCIES = QueueTraversalDependencies(
    list_active_orders=list_active_orders,
    claim_service_order=claim_service_order,
    release_service_order_claim=release_service_order_claim,
    update_order_state=update_order_state,
    mark_order_done=mark_order_done,
    run_service_order=run_service_order,
    update_state_from_report=_update_state_from_report,
    delay_between_orders=_delay_between_orders,
)


def run_rapid_queue_with_settings(
    settings: Settings,
    *,
    initial_confirmed_reservations: int = 0,
    initial_confirmed_order_ids: set[str] | None = None,
    cancel_event: threading.Event | None = None,
    on_order_start: Callable[[ServiceOrderCandidate | ServiceOrderRuntime], None] | None = None,
    on_check: Callable[..., None] | None = None,
    on_post_review_start: Callable[[], None] | None = None,
    skip_order_ids: set[str] | None = None,
    follow_up_order_ids: set[str] | None = None,
    target_order_ids: tuple[str, ...] | None = None,
    inter_order_delay_enabled: bool = True,
    stop_on_available_without_reserve: bool = True,
    dependencies: QueueTraversalDependencies = DEFAULT_QUEUE_TRAVERSAL_DEPENDENCIES,
) -> RunReport:
    initial_order_ids = set(initial_confirmed_order_ids or set())
    checked_orders = 0
    confirmed_reservations = initial_confirmed_reservations
    uncertain_reservations = 0
    failed_orders = 0
    results: list[dict[str, str]] = []
    deferred_reports: list[RunReport] = []
    confirmed_order_ids = list(initial_order_ids)
    completion_reason = "orders_exhausted"
    opportunity_queue = target_order_ids is not None
    opportunity_started = time.monotonic()
    opportunity_deadline = (
        time.monotonic() + settings.opportunity_handoff_max_seconds
        if opportunity_queue
        else None
    )
    lease_owner = f"queue-{uuid4().hex}"
    with ExitStack() as claims:
        # La consulta ya excluye ordenes terminadas; por eso la cola
        # empieza siempre en la orden pendiente de mayor prioridad.
        skipped_orders = skip_order_ids or set()
        orders = [
            order
            for order in (
                dependencies.list_active_orders(settings, order_ids=target_order_ids)
                if target_order_ids is not None
                else dependencies.list_active_orders(settings, include_constrained=False)
            )
            if order.order_id not in skipped_orders
        ]
        if target_order_ids is not None:
            order_positions = {
                order_id: index for index, order_id in enumerate(target_order_ids)
            }
            orders.sort(
                key=lambda candidate: order_positions.get(
                    candidate.order_id,
                    len(order_positions),
                )
            )
            orders = orders[: settings.opportunity_handoff_max_candidates]
        queued_order_ids = {order.order_id for order in orders}
        for order in dependencies.list_active_orders(
            settings, order_ids=follow_up_order_ids or set()
        ):
            if order.order_id in skipped_orders or order.order_id in queued_order_ids:
                continue
            orders.append(order)
            queued_order_ids.add(order.order_id)
        if not orders:
            details = {
                "checked_orders": 0,
                "confirmed_reservations": 0,
                "uncertain_reservations": 0,
                "failed_orders": 0,
                "results": [],
                "completion_reason": completion_reason,
                "opportunity_queue": opportunity_queue,
                "opportunity_elapsed_seconds": round(
                    time.monotonic() - opportunity_started,
                    3,
                ),
            }
            if confirmed_order_ids:
                if on_post_review_start is not None:
                    on_post_review_start()
                details["post_reservation_reviews"] = review_confirmed_orders_after_queue(
                    settings,
                    confirmed_order_ids,
                    cancel_event=cancel_event,
                )
            return RunReport(
                status="completed",
                message="No quedan ordenes pendientes para la cola rapida.",
                exit_code=0,
                details=details,
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
            if (
                opportunity_deadline is not None
                and time.monotonic() >= opportunity_deadline
            ):
                completion_reason = "opportunity_window_expired"
                logger.info(
                    "Stopping opportunity queue after %s seconds",
                    settings.opportunity_handoff_max_seconds,
                )
                break
            # El valor 0 significa todos los pendientes; un valor positivo
            # conserva un limite opcional de reservas confirmadas por ejecucion.
            if _reservation_limit_reached(settings, confirmed_reservations):
                completion_reason = "reservation_limit"
                logger.info(
                    "Queue reservation limit reached: %s",
                    settings.queue_max_reservations_per_run,
                )
                break

            if not dependencies.claim_service_order(
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
                dependencies.release_service_order_claim,
                order.order_id,
                owner_token=lease_owner,
                settings=settings,
            )
            try:
                checked_orders += 1
                if on_order_start is not None:
                    on_order_start(order)
                report = dependencies.run_service_order(
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
            dependencies.update_state_from_report(settings, order, report)
            outcome = classify_order_report(report)
            if outcome is OrderReportOutcome.BLOCKED:
                logger.info(
                    "Skipping order %s temporarily because the available appointment "
                    "does not match order rules.",
                    order.order_id,
                )
                if has_more_orders and inter_order_delay_enabled:
                    dependencies.delay_between_orders(settings, cancel_event=cancel_event)
                continue
            if outcome is OrderReportOutcome.CAPTCHA_REJECTED:
                cooldown = settings.captcha_rejection_cooldown_seconds
                failed_orders += 1
                dependencies.update_order_state(
                    order.order_id,
                    status=report.status,
                    message=report.message,
                    exit_code=report.exit_code,
                    backoff_seconds=cooldown,
                    settings=settings,
                )
                logger.warning(
                    "Order %s had an explicit CAPTCHA rejection; applying a %s-second "
                    "order cooldown and continuing the queue",
                    order.order_id,
                    cooldown,
                )
                if has_more_orders and inter_order_delay_enabled:
                    dependencies.delay_between_orders(settings, cancel_event=cancel_event)
                continue
            if report.exit_code != 0 or report.status == "error":
                failed_orders += 1

            if bool((report.details or {}).get("credential_error")):
                logger.error(
                    "Order %s was paused because its credential could not be decrypted",
                    order.order_id,
                )
                if has_more_orders and inter_order_delay_enabled:
                    dependencies.delay_between_orders(settings, cancel_event=cancel_event)
                continue

            if outcome is OrderReportOutcome.TERMINAL_STAGE:
                # Estados terminales de la etapa y registered excluyen al
                # orden de ejecuciones futuras.
                dependencies.mark_order_done(
                    order.order_id,
                    status=order_done_status_from_report(report),
                    settings=settings,
                )
                logger.info("Order marked as done: %s", order.order_id)
                if has_more_orders and inter_order_delay_enabled:
                    dependencies.delay_between_orders(settings, cancel_event=cancel_event)
                continue

            if outcome is OrderReportOutcome.REGISTERED:
                confirmed_reservations += 1
                confirmed_order_ids.append(order.order_id)
                dependencies.mark_order_done(order.order_id, settings=settings)
                logger.info("Reservation confirmed for order: %s", order.order_id)
                if (
                    has_more_orders
                    and inter_order_delay_enabled
                    and not _reservation_limit_reached(
                        settings,
                        confirmed_reservations,
                    )
                ):
                    dependencies.delay_between_orders(settings, cancel_event=cancel_event)
                continue

            if outcome is OrderReportOutcome.RESERVATION_UNCONFIRMED:
                completion_reason = "reservation_unconfirmed"
                uncertain_reservations += 1
                dependencies.update_order_state(
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
                completion_reason = "technical_error"
                # Un fallo tecnico o ambiguo detiene la cola para no
                # saltar la orden prioritaria ni repetir el problema en otras cuentas.
                if report.status == "unknown":
                    failed_orders += 1
                    dependencies.update_order_state(
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
                completion_reason = "availability_without_auto_reserve"
                logger.info(
                    "Stopping queue after availability alert with AUTO_RESERVE=false: %s",
                    order.order_id,
                )
                break

            if report.status in {"unavailable", "partial", "available", "completed"}:
                if opportunity_queue and report.status == "unavailable":
                    completion_reason = "opportunity_disappeared"
                    logger.info(
                        "Stopping opportunity queue because order %s confirmed no "
                        "remaining availability",
                        order.order_id,
                    )
                    break
                logger.info(
                    "Continuing queue after routine result for order %s",
                    order.order_id,
                )
                if has_more_orders and inter_order_delay_enabled:
                    dependencies.delay_between_orders(settings, cancel_event=cancel_event)
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
            "completion_reason": completion_reason,
            "opportunity_queue": opportunity_queue,
            "opportunity_candidate_limit": (
                settings.opportunity_handoff_max_candidates
                if opportunity_queue
                else None
            ),
            "opportunity_window_seconds": (
                settings.opportunity_handoff_max_seconds if opportunity_queue else None
            ),
            "opportunity_elapsed_seconds": round(
                time.monotonic() - opportunity_started,
                3,
            ),
        },
    )
    review_results: list[dict[str, str]] = []
    if (
        report.status == "completed"
        and completion_reason
        in {
            "orders_exhausted",
            "opportunity_disappeared",
            "opportunity_window_expired",
        }
        and confirmed_order_ids
    ):
        if on_post_review_start is not None:
            on_post_review_start()
        review_results = review_confirmed_orders_after_queue(
            settings,
            confirmed_order_ids,
            cancel_event=cancel_event,
        )
        report.details["post_reservation_reviews"] = review_results
        deferred_reports = replace_reports_with_reviewed_evidence(
            deferred_reports,
            review_results,
        )
    notify_deferred_queue_summary(report, settings, deferred_reports)
    for review in review_results:
        order_id = review.get("order_id")
        if (
            review.get("status") == "completed"
            and order_id
            and order_id not in initial_order_ids
        ):
            enqueue_whatsapp_automation_job(
                order_id,
                "reservation_album",
                settings=settings,
            )
    return report
