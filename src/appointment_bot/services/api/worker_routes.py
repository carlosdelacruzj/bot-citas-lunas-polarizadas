from __future__ import annotations

from dataclasses import asdict
from typing import Any

from appointment_bot.config import load_settings
from appointment_bot.services.postgres_database import get_worker_state


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
        return worker_controller.status()
    settings = load_settings(require_login=False)
    payload = asdict(get_worker_state(settings))
    payload["worker_running"] = False
    payload["continuous_worker_enabled"] = settings.continuous_worker_enabled
    return payload
