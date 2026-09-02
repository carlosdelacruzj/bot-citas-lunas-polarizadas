from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.core.statuses import sanitize_details
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _detail_text,
    _now,
    _settings,
    init_database,
)
from appointment_bot.db.whatsapp_messages import archive_whatsapp_evidence


def replace_confirmed_reservation_evidence(
    order_id: str,
    screenshot_path: Path,
    *,
    settings: Settings | None = None,
) -> Path:
    settings = _settings(settings)
    init_database(settings)
    archived = archive_whatsapp_evidence(order_id, [screenshot_path])
    if archived is None:
        raise ValueError("La revision no produjo una evidencia PNG segura.")
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE reservations
            SET evidence_path = %s, updated_at = %s
            WHERE reservation_id = (
                SELECT reservation_id
                FROM reservations
                WHERE order_id = %s AND status = 'confirmed'
                ORDER BY reserved_at DESC, created_at DESC
                LIMIT 1
            )
            RETURNING reservation_id
            """,
            (str(archived), _now(), order_id),
        ).fetchone()
    if row is None:
        archived.unlink(missing_ok=True)
        raise ValueError("La orden no tiene una reserva confirmada para actualizar.")
    return archived


def create_reservation_attempt(
    attempt_id: str,
    order_id: str,
    *,
    details: dict[str, Any] | None,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    details = sanitize_details(details) or {}
    now = _now()
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO reservation_attempts (
                attempt_id, order_id, idempotency_key, status, site,
                appointment_date, appointment_hour, details_json, created_at, updated_at
            ) VALUES (%s, %s, %s, 'intent', %s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                details_json = COALESCE(reservation_attempts.details_json, excluded.details_json),
                updated_at = excluded.updated_at
            """,
            (
                attempt_id,
                order_id,
                attempt_id,
                _detail_text(details, "sede"),
                _detail_text(details, "fecha"),
                _detail_text(details, "hora"),
                Jsonb(details) if details else None,
                now,
                now,
            ),
        )


def mark_reservation_attempt_pending(
    attempt_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE reservation_attempts
            SET status = 'pending', submitted_at = COALESCE(submitted_at, %s), updated_at = %s
            WHERE attempt_id = %s AND status = 'intent'
            """,
            (now, now, attempt_id),
        )


def resolve_reservation_attempt(
    attempt_id: str,
    status: str,
    *,
    run_id: str | None = None,
    evidence_path: str | None = None,
    settings: Settings | None = None,
) -> None:
    if status not in {"confirmed", "rejected", "unknown"}:
        raise ValueError(f"Invalid reservation attempt status: {status}")
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    resolved_at = now if status in {"confirmed", "rejected"} else None
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE reservation_attempts
            SET status = %s, run_id = COALESCE(%s, run_id),
                evidence_path = COALESCE(%s, evidence_path),
                resolved_at = %s, updated_at = %s
            WHERE attempt_id = %s
              AND status IN ('intent', 'pending', 'unknown')
            """,
            (status, run_id, evidence_path, resolved_at, now, attempt_id),
        )


def get_active_reservation_attempt(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        return connection.execute(
            """
            SELECT attempt_id, status, site, appointment_date, appointment_hour
            FROM reservation_attempts
            WHERE order_id = %s AND status IN ('intent', 'pending', 'unknown')
            ORDER BY created_at DESC LIMIT 1
            """,
            (order_id,),
        ).fetchone()
