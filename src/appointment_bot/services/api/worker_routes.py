from __future__ import annotations

import logging
import re
from dataclasses import asdict
from http import HTTPStatus
from typing import Any

from appointment_bot.config import Settings, load_settings
from appointment_bot.db.order_state import (
    list_pending_order_backoffs,
    release_order_backoffs,
)
from appointment_bot.db.remote_control_audit import record_remote_control_audit
from appointment_bot.db.worker_commands import (
    enqueue_worker_command,
    list_worker_commands,
)
from appointment_bot.db.worker_state import get_worker_state, is_worker_lease_active
from appointment_bot.services.api.http import error_payload
from appointment_bot.worker.recovery import portal_defense_signal

logger = logging.getLogger(__name__)

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
    settings = load_settings(require_login=False)
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
        "captcha_shadow_enabled": settings.captcha_shadow_enabled,
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
            requested_by=normalize_worker_actor(requested_by),
        )
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    record_worker_control_audit(
        command=queued.command,
        requested_by=queued.requested_by,
        status="accepted",
        operation_id=queued.command_id,
        detail="control_path=persisted_command",
    )
    return HTTPStatus.ACCEPTED, {
        "status": "queued",
        "command_id": queued.command_id,
        "command": queued.command,
        "message": "Worker command queued for the continuous worker.",
    }


def enqueue_restart_with_safe_backoff_release_payload(
    *,
    requested_by: str | None = None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    status, payload = enqueue_worker_command_payload(
        "restart",
        requested_by=requested_by,
    )
    if status != HTTPStatus.ACCEPTED:
        return status, payload

    settings = load_settings(require_login=False)
    command_id = str(payload.get("command_id") or "")
    try:
        pending = list_pending_order_backoffs(settings=settings)
        eligible_order_ids = tuple(
            str(row["order_id"])
            for row in pending
            if _safe_technical_backoff(row)
        )
        released_order_ids = release_order_backoffs(
            eligible_order_ids,
            settings=settings,
        )
    except Exception as exc:
        logger.exception("Could not release safe technical order backoffs")
        record_remote_control_audit(
            actor=normalize_worker_actor(requested_by),
            action="release_safe_backoffs",
            status="failed",
            target_type="worker",
            target_id="continuous_worker",
            operation_id=command_id or None,
            detail=f"restart_queued=true error={type(exc).__name__}",
            settings=settings,
        )
        return HTTPStatus.INTERNAL_SERVER_ERROR, error_payload(
            "backoff_release_failed",
            "El reinicio fue solicitado, pero no se pudieron liberar los backoffs seguros.",
            command_id=command_id or None,
            command="restart",
        )

    protected_count = max(0, len(pending) - len(released_order_ids))
    record_remote_control_audit(
        actor=normalize_worker_actor(requested_by),
        action="release_safe_backoffs",
        status="applied",
        target_type="worker",
        target_id="continuous_worker",
        operation_id=command_id or None,
        detail=f"released={len(released_order_ids)} protected={protected_count}",
        settings=settings,
    )
    payload.update(
        {
            "message": "Reinicio solicitado con liberacion de backoffs tecnicos seguros.",
            "released_backoff_count": len(released_order_ids),
            "protected_backoff_count": protected_count,
        }
    )
    return status, payload


def _safe_technical_backoff(row: dict[str, Any]) -> bool:
    if str(row.get("last_status") or "").strip().lower() != "error":
        return False
    if str(row.get("latest_run_status") or "").strip().lower() != "error":
        return False
    if bool(row.get("reservation_attempted")) or bool(row.get("has_active_attempt")):
        return False
    if str(row.get("submission_outcome") or "").strip():
        return False
    return portal_defense_signal(str(row.get("last_message") or "")) is None


def normalize_worker_actor(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return "admin_api"
    if len(normalized) > 64 or re.fullmatch(r"[A-Za-z0-9:_-]+", normalized) is None:
        return "admin_api"
    return normalized


def record_worker_control_audit(
    *,
    command: str,
    requested_by: str | None,
    status: str,
    operation_id: str | None = None,
    detail: str | None = None,
    settings: Settings | None = None,
) -> None:
    try:
        record_remote_control_audit(
            actor=normalize_worker_actor(requested_by),
            action=command,
            status=status,
            target_type="worker",
            target_id="continuous_worker",
            operation_id=operation_id,
            detail=detail,
            settings=settings,
        )
    except Exception:
        logger.exception("Could not persist worker control audit for %s", command)


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
