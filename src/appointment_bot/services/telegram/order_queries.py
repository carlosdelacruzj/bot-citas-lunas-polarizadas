from __future__ import annotations

import logging
import time
from typing import Any

from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.constants import WORKER_COMMAND_TIMEOUT_SECONDS

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _wait_for_order_preflight(
    admin_api: AdminApiClient, order_id: str
) -> dict[str, Any]:
    deadline = time.monotonic() + WORKER_COMMAND_TIMEOUT_SECONDS
    last_order: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_order = admin_api.get_service_order(order_id)
        if str(last_order.get("preflight_status") or "") not in {
            "",
            "pending",
            "running",
        }:
            return last_order
        time.sleep(2)
    return last_order
