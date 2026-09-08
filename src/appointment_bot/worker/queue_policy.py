from __future__ import annotations

import logging
import random
import threading
import time

from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.core.models import RunReport, ServiceOrderRuntime
from appointment_bot.db.order_state import update_order_state
from appointment_bot.services.order_runtime import OrderReportOutcome, classify_order_report

logger = logging.getLogger(__name__)


def update_state_from_report(
    order: ServiceOrderRuntime, report: RunReport, *, runtime_settings: RuntimeSettings
) -> None:
    if report.status in {"skipped", "unknown", "reservation_unconfirmed"}:
        return
    outcome = classify_order_report(report)
    if outcome is OrderReportOutcome.CAPTCHA_REJECTED:
        return
    update_order_state(
        order.order_id,
        status=report.status,
        message=report.message,
        exit_code=report.exit_code,
        backoff_seconds=None,
        settings=runtime_settings,
    )


def reservation_limit_reached(
    confirmed_reservations: int, *, runtime_settings: RuntimeSettings
) -> bool:
    limit = runtime_settings.queue_max_reservations_per_run
    return limit > 0 and confirmed_reservations >= limit


def delay_between_orders(
    *, cancel_event: threading.Event | None = None, runtime_settings: RuntimeSettings
) -> None:
    if runtime_settings.queue_delay_max_seconds <= 0:
        return
    delay = random.randint(
        runtime_settings.queue_delay_min_seconds, runtime_settings.queue_delay_max_seconds
    )
    if delay <= 0:
        return
    logger.info("Waiting %s seconds before the next queued order", delay)
    if cancel_event is not None:
        cancel_event.wait(delay)
    else:
        time.sleep(delay)
