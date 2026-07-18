from __future__ import annotations

import re
from dataclasses import asdict
from http import HTTPStatus
from typing import Any

from appointment_bot.config import load_settings
from appointment_bot.db.worker_commands import (
    enqueue_worker_command,
    list_worker_commands,
)
from appointment_bot.db.worker_state import get_worker_state, is_worker_lease_active
from appointment_bot.services.api.http import error_payload

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
    payload["worker_running"] = is_worker_lease_active(settings)
    payload["continuous_worker_enabled"] = settings.continuous_worker_enabled
    return public_worker_payload(payload)


def public_worker_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {field: payload.get(field) for field in PUBLIC_WORKER_FIELDS if field in payload}


def enqueue_worker_command_payload(
    command: str,
    *,
    requested_by: str | None = None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        queued = enqueue_worker_command(
            command,
            requested_by=_requested_by(requested_by),
        )
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    return HTTPStatus.ACCEPTED, {
        "status": "queued",
        "command_id": queued.command_id,
        "command": queued.command,
        "message": "Worker command queued for the continuous worker.",
    }


def _requested_by(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return "admin_api"
    if len(normalized) > 64 or re.fullmatch(r"[A-Za-z0-9:_-]+", normalized) is None:
        return "admin_api"
    return normalized


def list_worker_commands_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    limit = _query_int(query, "limit", default=20)
    return {
        "commands": [
            {
                "command_id": command.command_id,
                "command": command.command,
                "status": command.status,
                "requested_by": command.requested_by,
                "requested_at": command.requested_at,
                "claimed_at": command.claimed_at,
                "processed_at": command.processed_at,
                "error_message": command.error_message,
            }
            for command in list_worker_commands(limit=limit)
        ]
    }


def _query_int(query: dict[str, list[str]], name: str, *, default: int) -> int:
    try:
        return int(query.get(name, [str(default)])[0])
    except (TypeError, ValueError):
        return default
