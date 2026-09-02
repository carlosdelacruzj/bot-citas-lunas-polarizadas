from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _now,
    _settings,
    init_database,
)


def mark_order_preflight_pending(
    order_id: str,
    *,
    new_cycle: bool = True,
    settings: Settings | None = None,
) -> int:
    return _set_preflight(
        order_id,
        status="pending",
        message="Validacion de acceso pendiente.",
        cycle_increment=1 if new_cycle else 0,
        settings=settings,
    )


def mark_order_preflight_running(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> int:
    return _set_preflight(
        order_id,
        status="running",
        message="Validando acceso, identidad y tramites en el portal.",
        started=True,
        settings=settings,
    )


def mark_order_preflight_validated(
    order_id: str,
    *,
    applicant_name: str,
    details: dict[str, Any],
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    applicant_name = " ".join(applicant_name.split())
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            "SELECT applicant_id FROM service_orders WHERE order_id = %s",
            (order_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Service order not found: {order_id}")
        connection.execute(
            "UPDATE applicants SET full_name = %s, updated_at = %s WHERE applicant_id = %s",
            (applicant_name, now, row["applicant_id"]),
        )
        connection.execute(
            """
            UPDATE order_state
            SET preflight_status = 'validated',
                preflight_message = %s,
                preflight_validated_at = %s,
                preflight_details = %s,
                last_status = NULL,
                last_message = NULL,
                next_allowed_at = NULL,
                consecutive_errors = 0,
                credential_failures = 0
            WHERE order_id = %s
            """,
            (
                "Acceso, identidad y tramites validados correctamente.",
                now,
                Jsonb(details),
                order_id,
            ),
        )
        connection.execute(
            """
            UPDATE service_orders
            SET status = CASE WHEN status = 'paused' THEN 'ready' ELSE status END,
                updated_at = %s
            WHERE order_id = %s
            """,
            (now, order_id),
        )


def mark_order_preflight_failed(
    order_id: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> int:
    return _set_preflight(
        order_id,
        status="failed",
        message=message,
        details=details,
        settings=settings,
    )


def _set_preflight(
    order_id: str,
    *,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
    started: bool = False,
    cycle_increment: int = 0,
    settings: Settings | None = None,
) -> int:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET status = CASE WHEN status = 'ready' THEN 'paused' ELSE status END,
                updated_at = %s
            WHERE order_id = %s
            """,
            (now, order_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Service order not found: {order_id}")
        row = connection.execute(
            """
            INSERT INTO order_state (
                order_id, preflight_status, preflight_message,
                preflight_started_at, preflight_validated_at, preflight_details,
                preflight_cycle
            )
            VALUES (%s, %s, %s, %s, NULL, %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                preflight_status = excluded.preflight_status,
                preflight_message = excluded.preflight_message,
                preflight_started_at = CASE
                    WHEN %s THEN excluded.preflight_started_at
                    ELSE order_state.preflight_started_at
                END,
                preflight_validated_at = NULL,
                preflight_details = excluded.preflight_details,
                preflight_cycle = order_state.preflight_cycle + excluded.preflight_cycle
            RETURNING preflight_cycle
            """,
            (
                order_id,
                status,
                message,
                now if started else None,
                Jsonb(details),
                cycle_increment,
                started,
            ),
        ).fetchone()
    return int(row["preflight_cycle"])
