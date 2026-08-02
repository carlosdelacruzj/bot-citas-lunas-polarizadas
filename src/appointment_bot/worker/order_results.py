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
    list_compatible_orders_for_slot,
    mark_order_done,
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
    compatible_handoff_order_ids: tuple[str, ...] = ()
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
    if outcome is OrderReportOutcome.PAUSED:
        return ObserverOrderDecision()
    if outcome is OrderReportOutcome.BLOCKED:
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            backoff_seconds=None,
            settings=settings,
        )
        logger.info(
            "Order %s remains eligible after a slot was blocked by its rules",
            order.order_id,
        )
        compatible_order_ids = _compatible_handoff_order_ids(
            settings,
            order,
            report,
        )
        return ObserverOrderDecision(
            compatible_handoff_order_ids=compatible_order_ids,
            reset_errors=True,
        )
    if outcome is OrderReportOutcome.TERMINAL_STAGE:
        mark_order_done(
            order.order_id,
            status=order_done_status_from_report(report),
            settings=settings,
        )
        return ObserverOrderDecision(reset_errors=True)
    if outcome is OrderReportOutcome.REGISTERED:
        mark_order_done(order.order_id, settings=settings)
        return ObserverOrderDecision(
            queue_requested=True,
            rapid_queue_initial_confirmed=1,
            confirmed_reservations=1,
            confirmed_order_ids=(order.order_id,),
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
    if outcome is OrderReportOutcome.CAPTCHA_REJECTED:
        cooldown = settings.captcha_rejection_cooldown_seconds
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            backoff_seconds=cooldown,
            settings=settings,
        )
        send_telegram_message(
            settings,
            f"La orden {order.order_id} tuvo dos rechazos explicitos de CAPTCHA. "
            f"Se reintentara esa orden en {cooldown} segundos; el worker "
            "continuara de inmediato con los demas clientes elegibles.",
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


def _compatible_handoff_order_ids(
    settings: Settings,
    order: ServiceOrderCandidate | ServiceOrderRuntime,
    report: RunReport,
) -> tuple[str, ...]:
    details = report.details or {}
    appointment_date = str(
        details.get("fecha") or details.get("appointment_date") or ""
    ).strip()
    appointment_hour = str(
        details.get("hora") or details.get("appointment_hour") or ""
    ).strip()
    if not appointment_date or not appointment_hour:
        return ()
    try:
        compatible_orders = list_compatible_orders_for_slot(
            appointment_date,
            appointment_hour,
            exclude_order_ids={order.order_id},
            limit=settings.observer_active_order_limit,
            settings=settings,
        )
    except Exception:
        logger.exception(
            "Could not find compatible handoff orders for slot %s %s",
            appointment_date,
            appointment_hour,
        )
        return ()
    order_ids = tuple(candidate.order_id for candidate in compatible_orders)
    if order_ids:
        logger.info(
            "Blocked slot %s %s will be handed off immediately to compatible orders: %s",
            appointment_date,
            appointment_hour,
            ", ".join(order_ids),
        )
    else:
        logger.info(
            "Blocked slot %s %s has no compatible active orders",
            appointment_date,
            appointment_hour,
        )
    return order_ids


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
