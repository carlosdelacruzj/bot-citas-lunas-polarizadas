from __future__ import annotations

from dataclasses import asdict
from typing import Any

from appointment_bot.config import load_settings
from appointment_bot.services.postgres_worker import get_worker_state

PUBLIC_WORKER_FIELDS = {
    "phase",
    "paused",
    "current_order_id",
    "masked_account",
    "session_started_at",
    "last_check_at",
    "next_check_at",
    "confirmed_reservations",
    "consecutive_errors",
    "last_error",
    "updated_at",
    "worker_running",
    "worker_starting",
    "continuous_worker_enabled",
}


def health_payload(worker_controller: Any | None) -> tuple[bool, dict[str, Any]]:
    if worker_controller is None:
        healthy, reason = True, "api_only"
        worker_running = False
    else:
        healthy, reason = worker_controller.health()
        worker_running = worker_controller.is_running
    return healthy, {
        "status": "ok" if healthy else "degraded",
        "message": (
            "Appointment bot local API is running."
            if healthy
            else "Appointment bot API is running, but the worker is stopped."
        ),
        "worker_running": worker_running,
        "reason": reason,
    }


def worker_payload(worker_controller: Any | None) -> dict[str, Any]:
    if worker_controller is not None:
        return public_worker_payload(worker_controller.status())
    settings = load_settings(require_login=False)
    payload = asdict(get_worker_state(settings))
    payload["worker_running"] = False
    payload["continuous_worker_enabled"] = settings.continuous_worker_enabled
    return public_worker_payload(payload)


def public_worker_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {field: payload.get(field) for field in PUBLIC_WORKER_FIELDS if field in payload}
