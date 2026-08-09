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
    list_compatible_orders_for_opportunities,
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
        compatible_order_ids = compatible_handoff_order_ids(
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
        compatible_order_ids = compatible_handoff_order_ids(
            settings,
            order,
            report,
        )
        return ObserverOrderDecision(
            queue_requested=True,
            rapid_queue_initial_confirmed=1,
            confirmed_reservations=1,
            confirmed_order_ids=(order.order_id,),
            compatible_handoff_order_ids=compatible_order_ids,
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


def compatible_handoff_order_ids(
    settings: Settings,
    order: ServiceOrderCandidate | ServiceOrderRuntime,
    report: RunReport,
) -> tuple[str, ...]:
    details = report.details or {}
    opportunities = observed_opportunities(details)
    if not opportunities:
        return ()
    try:
        compatible_orders = list_compatible_orders_for_opportunities(
            opportunities,
            exclude_order_ids={order.order_id},
            limit=settings.opportunity_handoff_max_candidates,
            settings=settings,
        )
    except Exception:
        logger.exception(
            "Could not find compatible handoff orders for %s observed opportunities",
            len(opportunities),
        )
        return ()
    order_ids = tuple(candidate.order_id for candidate in compatible_orders)
    if order_ids:
        logger.info(
            "%s observed opportunities will be handed off immediately to compatible "
            "orders: %s",
            len(opportunities),
            ", ".join(order_ids),
        )
    else:
        logger.info(
            "%s observed opportunities have no compatible active orders",
            len(opportunities),
        )
    return order_ids


def observed_opportunities(details: dict[str, object]) -> tuple[tuple[str, str], ...]:
    observation = details.get("selection_observation")
    raw_appointments = (
        observation.get("observed_appointments")
        if isinstance(observation, dict)
        else None
    )
    opportunities: list[tuple[str, str]] = []
    observed_dates: set[str] = set()
    if isinstance(raw_appointments, list):
        for item in raw_appointments:
            if not isinstance(item, dict):
                continue
            date_text = str(item.get("date") or "").strip()
            hour_text = str(item.get("hour") or "").strip()
            if date_text:
                opportunities.append((date_text, hour_text))
                observed_dates.add(date_text)

    visible_dates = observation.get("visible_dates") if isinstance(observation, dict) else None
    if isinstance(visible_dates, list):
        for value in visible_dates:
            date_text = str(value or "").strip()
            if date_text and date_text not in observed_dates:
                opportunities.append((date_text, ""))

    fallback_date = str(
        details.get("fecha")
        or details.get("appointment_date")
        or details.get("blocked_evidence_date")
        or ""
    ).strip()
    fallback_hour = str(
        details.get("hora")
        or details.get("appointment_hour")
        or details.get("blocked_evidence_hour")
        or ""
    ).strip()
    if fallback_date:
        opportunities.append((fallback_date, fallback_hour))
    return tuple(dict.fromkeys(opportunities))


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
