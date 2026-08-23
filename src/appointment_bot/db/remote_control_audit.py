from __future__ import annotations

from uuid import uuid4

from psycopg import Connection

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _settings,
    init_database,
)
from appointment_bot.utils.sanitization import sanitize_text

VALID_AUDIT_STATUSES = {
    "accepted",
    "applied",
    "failed",
    "cancelled",
    "denied",
    "rate_limited",
    "started",
}


def record_remote_control_audit(
    *,
    actor: str,
    action: str,
    status: str,
    target_type: str | None = None,
    target_id: str | None = None,
    operation_id: str | None = None,
    detail: str | None = None,
    settings: Settings | None = None,
) -> str:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        return record_remote_control_audit_in_connection(
            connection,
            actor=actor,
            action=action,
            status=status,
            target_type=target_type,
            target_id=target_id,
            operation_id=operation_id,
            detail=detail,
        )


def record_remote_control_audit_in_connection(
    connection: Connection,
    *,
    actor: str,
    action: str,
    status: str,
    target_type: str | None = None,
    target_id: str | None = None,
    operation_id: str | None = None,
    detail: str | None = None,
) -> str:
    """Persist an audit row using the caller's transaction."""
    normalized_status = status.strip().lower()
    if normalized_status not in VALID_AUDIT_STATUSES:
        raise ValueError(f"Unsupported remote-control audit status: {status}")
    audit_id = f"remote-audit-{uuid4().hex}"
    safe_detail = sanitize_text(detail.strip())[:240] if detail else None
    connection.execute(
        """
        INSERT INTO remote_control_audit (
            audit_id, actor, action, target_type, target_id,
            status, operation_id, detail
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            audit_id,
            actor[:80],
            action[:80],
            target_type[:40] if target_type else None,
            target_id[:100] if target_id else None,
            normalized_status,
            operation_id[:80] if operation_id else None,
            safe_detail,
        ),
    )
    return audit_id
