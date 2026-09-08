from __future__ import annotations

import hashlib
import logging

from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.validation import _valid_order_id

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _telegram_actor(chat_id: str, user_id: str | None = None) -> str:
    effective_user_id = user_id or chat_id
    identity = f"chat:{chat_id}|user:{effective_user_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"telegram:{digest}"


def _audit_target(arguments: str) -> str | None:
    candidate = arguments.strip().split(maxsplit=1)[0] if arguments.strip() else ""
    return candidate if _valid_order_id(candidate) else None


def _record_audit_safe(
    *,
    admin_api: AdminApiClient,
    actor: str,
    action: str,
    status: str,
    target_type: str | None = None,
    target_id: str | None = None,
    operation_id: str | None = None,
    detail: str | None = None,
) -> None:
    try:
        admin_api.record_remote_control_audit(
            actor=actor,
            action=action,
            status=status,
            target_type=target_type,
            target_id=target_id,
            operation_id=operation_id,
            detail=detail,
        )
    except Exception:
        logger.warning("Could not persist remote-control audit action=%s", action)
