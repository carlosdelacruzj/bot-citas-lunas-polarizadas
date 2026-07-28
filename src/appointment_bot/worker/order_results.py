from __future__ import annotations

import logging
from dataclasses import dataclass

from appointment_bot.config import Settings
from appointment_bot.core.models import (
    RunReport,
    ServiceOrderCandidate,
    ServiceOrderRuntime,
)
from appointment_bot.db.orders import (
    EXCLUSIVE_PRIORITY_THRESHOLD,
    list_observer_orders,
    mark_order_done,
    promote_orders_matching_reserved_slot,
    update_order_state,
)
from appointment_bot.services.notifier import send_telegram_message
from appointment_bot.services.order_runtime import (
    OrderReportOutcome,
    classify_order_report,
    order_done_status_from_report,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObserverOrderDecision:
    queue_requested: bool = False
    rapid_queue_initial_confirmed: int = 0
    confirmed_reservations: int = 0
    confirmed_order_ids: tuple[str, ...] = ()
    follow_up_order_ids: tuple[str, ...] = ()
    reset_errors: bool = False
    requires_error_handling: bool = False


def handle_observer_order_report(
    settings: Settings,
    order: ServiceOrderCandidate | ServiceOrderRuntime,
    report: RunReport,
) -> ObserverOrderDecision:
    if bool((report.details or {}).get("credential_error")):
        _notify_credential_rejection(settings, order, report)
        return ObserverOrderDecision(reset_errors=True)

    outcome = classify_order_report(report)
    if bool((report.details or {}).get("deferred_to_higher_priority")):
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            settings=settings,
        )
        logger.info(
            "Observer %s deferred a detected slot; starting the priority queue",
            order.order_id,
        )
        higher_priority_order_ids = tuple(
            candidate.order_id
            for candidate in list_observer_orders(settings)
            if candidate.priority > order.priority
        )
        return ObserverOrderDecision(
            queue_requested=True,
            rapid_queue_initial_confirmed=0,
            follow_up_order_ids=higher_priority_order_ids,
            reset_errors=True,
        )
    if outcome is OrderReportOutcome.PAUSED:
        return ObserverOrderDecision()
    if outcome is OrderReportOutcome.BLOCKED:
        backoff_seconds = (
            None
            if order.priority >= EXCLUSIVE_PRIORITY_THRESHOLD
            else settings.order_rule_cooldown_seconds
        )
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            backoff_seconds=backoff_seconds,
            settings=settings,
        )
        if backoff_seconds is None:
            logger.info(
                "Exclusive order %s remains eligible after a slot was blocked by its rules",
                order.order_id,
            )
        return ObserverOrderDecision(reset_errors=True)
    if outcome is OrderReportOutcome.TERMINAL_STAGE:
        mark_order_done(
            order.order_id,
            status=order_done_status_from_report(report),
            settings=settings,
        )
        return ObserverOrderDecision(reset_errors=True)
    if outcome is OrderReportOutcome.REGISTERED:
        mark_order_done(order.order_id, settings=settings)
        promoted_orders = _promote_orders_matching_report_slot(settings, order, report)
        return ObserverOrderDecision(
            queue_requested=True,
            rapid_queue_initial_confirmed=1,
            confirmed_reservations=1,
            confirmed_order_ids=(order.order_id,),
            follow_up_order_ids=tuple(candidate.order_id for candidate in promoted_orders),
            reset_errors=True,
        )
    if outcome is OrderReportOutcome.RESERVATION_UNCONFIRMED:
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            backoff_seconds=settings.error_backoff_seconds,
            settings=settings,
        )
        send_telegram_message(
            settings,
            f"La orden {order.order_id} envio una reserva pero no se pudo "
            "confirmar automaticamente como Programado. Se pausa solo esa orden "
            "temporalmente para revision; el worker continuara con las demas "
            "ordenes elegibles.",
        )
        return ObserverOrderDecision(reset_errors=True)
    if report.status == "available":
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            settings=settings,
        )
        logger.info(
            "Observer %s detected availability without a confirmed reservation; "
            "the priority queue will not start",
            order.order_id,
        )
        return ObserverOrderDecision(reset_errors=True)
    if outcome is OrderReportOutcome.ROUTINE:
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            settings=settings,
        )
        return ObserverOrderDecision(reset_errors=True)
    return ObserverOrderDecision(requires_error_handling=True)


def _notify_credential_rejection(
    settings: Settings,
    order: ServiceOrderCandidate | ServiceOrderRuntime,
    report: RunReport,
) -> None:
    failures = int((report.details or {}).get("credential_failure_count") or 0)
    paused = bool((report.details or {}).get("credential_paused"))
    send_telegram_message(
        settings,
        (
            f"La orden {order.order_id} fue pausada despues de dos rechazos "
            "de contrasena. Actualiza la clave y reactiva la orden."
            if paused
            else f"La orden {order.order_id} tuvo su primer rechazo de contrasena; "
            "se intentara una vez mas en la siguiente rotacion."
        ),
    )
    logger.warning(
        "Credential rejection %s/2 for order %s; paused=%s",
        failures,
        order.order_id,
        paused,
    )


def _promote_orders_matching_report_slot(
    settings: Settings,
    order: ServiceOrderCandidate | ServiceOrderRuntime,
    report: RunReport,
) -> list[ServiceOrderCandidate]:
    promoted_orders = promote_orders_matching_reserved_slot(
        report.details or {},
        excluded_order_id=order.order_id,
        settings=settings,
    )
    if not promoted_orders:
        return []
    logger.info(
        "Promoted %s constrained order(s) after confirmed reservation %s: %s",
        len(promoted_orders),
        order.order_id,
        ", ".join(candidate.order_id for candidate in promoted_orders),
    )
    return promoted_orders
