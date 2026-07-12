from __future__ import annotations

import logging
import random
import threading
import time

from appointment_bot.config import Settings
from appointment_bot.db.order_state import update_order_state
from appointment_bot.domain import RunReport
from appointment_bot.services.database_models import ServiceOrderRuntime
from appointment_bot.services.order_runtime import OrderReportOutcome, classify_order_report

logger = logging.getLogger(__name__)


def update_state_from_report(
    settings: Settings,
    order: ServiceOrderRuntime,
    report: RunReport,
) -> None:
    if report.status in {"skipped", "unknown", "reservation_unconfirmed"}:
        return
    backoff_seconds = (
        settings.order_rule_cooldown_seconds
        if classify_order_report(report) is OrderReportOutcome.BLOCKED
        else None
    )

    update_order_state(
        order.order_id,
        status=report.status,
        message=report.message,
        exit_code=report.exit_code,
        backoff_seconds=backoff_seconds,
        settings=settings,
    )


def reservation_limit_reached(settings: Settings, confirmed_reservations: int) -> bool:
    limit = settings.queue_max_reservations_per_run
    return limit > 0 and confirmed_reservations >= limit


def delay_between_orders(
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
