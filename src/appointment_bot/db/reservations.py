from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.core.statuses import sanitize_details
from appointment_bot.db.common import (
    DEFAULT_RESERVATION_AMOUNT,
    _connection,
    _database_url,
    _detail_text,
    _id_from_value,
    _now,
    _operation_connection,
    _optional_text_value,
    _settings,
    init_database,
)
from appointment_bot.services.detail_helpers import appointment_datetime_details


def _record_reservation_for_order(
    order_id: str,
    report: object,
    *,
    confirmed: bool | None = None,
    settings: Settings | None = None,
    _connection_override: Connection | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    details = getattr(report, "details", None) or {}
    now = _now()
    run_id = getattr(report, "run_id", None)
    is_confirmed = (
        bool(getattr(report, "reservation_confirmed", False)) if confirmed is None else confirmed
    )
    appointment_date_raw, appointment_hour_raw = appointment_datetime_details(details)
    appointment_date = _optional_text_value(appointment_date_raw)
    appointment_hour = _optional_text_value(appointment_hour_raw)
    status = "confirmed" if is_confirmed else "unconfirmed"
    reservation_id = _id_from_value("reservation", f"{order_id}-{run_id or now}")
    with _operation_connection(settings, _connection_override) as connection:
        order = connection.execute(
            """
            SELECT order_id, charge_required
            FROM service_orders
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()
        if order is None:
            return
        connection.execute(
            """
            INSERT INTO reservations (
                reservation_id, order_id, run_id, status, site, appointment_date,
                appointment_hour, slots, evidence_path, details_json,
                reserved_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(reservation_id) DO UPDATE SET
                status = excluded.status,
                evidence_path = excluded.evidence_path,
                details_json = excluded.details_json,
                updated_at = excluded.updated_at
            """,
            (
                reservation_id,
                order_id,
                run_id,
                status,
                _detail_text(details, "sede"),
                appointment_date,
                appointment_hour,
                _detail_text(details, "cupos"),
                getattr(report, "screenshot_path", None),
                Jsonb(sanitize_details(details)) if details else None,
                now,
                now,
                now,
            ),
        )
        if status == "confirmed":
            no_charge = not bool(order["charge_required"])
            if not no_charge:
                connection.execute(
                    """
                    INSERT INTO payments (
                        payment_id, order_id, reservation_id, status, amount_agreed,
                        currency, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, 'pending', %s, 'PEN', %s, %s)
                    ON CONFLICT(payment_id) DO NOTHING
                    """,
                    (
                        _id_from_value("payment", order_id),
                        order_id,
                        reservation_id,
                        DEFAULT_RESERVATION_AMOUNT,
                        now,
                        now,
                    ),
                )
            connection.execute(
                """
                UPDATE service_orders
                SET status = CASE
                        WHEN status = 'paid' THEN 'paid'
                        ELSE %s
                    END,
                    updated_at = %s
                WHERE order_id = %s
                """,
                ("archived" if no_charge else "reserved_payment_pending", now, order_id),
            )


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
