from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import Connection

from appointment_bot.config import Settings
from appointment_bot.core.statuses import OrderStateStatus, ResultStatus
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _now,
    _operation_connection,
    _settings,
    init_database,
)
from appointment_bot.db.order_contacts import _service_order_identity
from appointment_bot.utils.sanitization import sanitize_text


def cleanup_expired_service_order_claims(settings: Settings | None = None) -> int:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET lease_owner = NULL,
                lease_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE lease_owner IS NOT NULL
              AND lease_expires_at <= CURRENT_TIMESTAMP
            """
        )
        return cursor.rowcount


def claim_service_order(
    order_id: str,
    *,
    owner_token: str,
    lease_seconds: int,
    settings: Settings | None = None,
) -> bool:
    """Atomically claim an eligible order for one worker."""
    if not owner_token.strip():
        raise ValueError("owner_token is required to claim a service order.")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be greater than zero.")
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders AS so
            SET lease_owner = %s,
                lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            WHERE so.order_id = %s
              AND so.status = 'ready'
              AND (
                  so.lease_owner = %s
                  OR so.lease_expires_at IS NULL
                  OR so.lease_expires_at <= CURRENT_TIMESTAMP
              )
            """,
            (owner_token, lease_seconds, order_id, owner_token),
        )
        return bool(cursor.rowcount)


def release_service_order_claim(
    order_id: str,
    *,
    owner_token: str,
    settings: Settings | None = None,
) -> bool:
    """Release a lease only when it is still owned by the caller."""
    if not owner_token.strip():
        return False
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET lease_owner = NULL,
                lease_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
              AND lease_owner = %s
            """,
            (order_id, owner_token),
        )
        return bool(cursor.rowcount)


def renew_service_order_claim(
    order_id: str,
    *,
    owner_token: str,
    lease_seconds: int,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
              AND lease_owner = %s
              AND lease_expires_at > CURRENT_TIMESTAMP
            """,
            (lease_seconds, order_id, owner_token),
        )
        return bool(cursor.rowcount)


def service_order_claim_owned(
    order_id: str,
    *,
    owner_token: str,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM service_orders
            WHERE order_id = %s
              AND status = 'ready'
              AND lease_owner = %s
              AND lease_expires_at > CURRENT_TIMESTAMP
            """,
            (order_id, owner_token),
        ).fetchone()
        return row is not None


def _update_applicant_name_for_order(
    order_id: str,
    full_name: str,
    *,
    settings: Settings | None = None,
    _connection_override: Connection | None = None,
) -> bool:
    full_name = " ".join(full_name.split())
    if not full_name:
        return False
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _operation_connection(settings, _connection_override) as connection:
        row = _service_order_identity(connection, order_id)
        if row is None:
            return False
        cursor = connection.execute(
            """
            UPDATE applicants
            SET full_name = %s, updated_at = %s
            WHERE applicant_id = %s
              AND (
                full_name IS NULL
                OR btrim(full_name) = ''
                OR btrim(full_name) <> %s
              )
            """,
            (full_name, now, row["applicant_id"], full_name),
        )
        return bool(cursor.rowcount)


def order_backoff_seconds(order_id: str, *, settings: Settings | None = None) -> int:
    row = _order_state_row(order_id, settings=settings)
    if row is None or not row["next_allowed_at"]:
        return 0
    try:
        next_allowed_at = datetime.fromisoformat(str(row["next_allowed_at"]))
    except ValueError:
        return 0
    return max(0, int((next_allowed_at - datetime.now(UTC)).total_seconds()))


def order_reservation_pending(order_id: str, *, settings: Settings | None = None) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT 1 FROM reservation_attempts
            WHERE order_id = %s AND status IN ('intent', 'pending', 'unknown')
            """,
            (order_id,),
        ).fetchone()
    if row is not None:
        return True
    state_row = _order_state_row(order_id, settings=settings)
    return state_row is not None and state_row["last_status"] in {
        OrderStateStatus.SUBMISSION_INTENT,
        OrderStateStatus.SUBMISSION_PENDING,
        OrderStateStatus.RESERVATION_UNCONFIRMED,
    }


def mark_order_submission_pending(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    _set_order_submission_state(
        order_id,
        OrderStateStatus.SUBMISSION_PENDING,
        "Se inicio el envio de una reserva; falta confirmar el resultado.",
        settings=settings,
    )


def mark_order_submission_intent(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    _set_order_submission_state(
        order_id,
        OrderStateStatus.SUBMISSION_INTENT,
        "Se detecto intencion de enviar una reserva.",
        settings=settings,
    )


def clear_order_submission_state(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE order_state
            SET last_status = NULL, last_message = NULL, next_allowed_at = NULL
            WHERE order_id = %s
            """,
            (order_id,),
        )


def order_submission_age_seconds(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> int | None:
    row = _order_state_row(order_id, settings=settings)
    if row is None or row["last_status"] not in {
        OrderStateStatus.SUBMISSION_INTENT,
        OrderStateStatus.SUBMISSION_PENDING,
        OrderStateStatus.RESERVATION_UNCONFIRMED,
    }:
        return None
    try:
        started_at = datetime.fromisoformat(str(row["last_run_at"]))
    except (TypeError, ValueError):
        return None
    return max(0, int((datetime.now(UTC) - started_at).total_seconds()))


def set_order_paused(order_id: str, paused: bool, *, settings: Settings | None = None) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET status = CASE WHEN %s THEN 'paused' ELSE 'ready' END,
                updated_at = %s
            WHERE order_id = %s
            """,
            (paused, now, order_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Service order not found: {order_id}")
        if not paused:
            connection.execute(
                """
                UPDATE order_state
                SET last_status = NULL, last_message = NULL, next_allowed_at = NULL,
                    consecutive_errors = 0, credential_failures = 0, programmed_at = NULL
                WHERE order_id = %s
                """,
                (order_id,),
            )


def has_active_child_service_orders(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM service_orders
            WHERE parent_order_id = %s
              AND status IN ('ready', 'paused', 'reserved_payment_pending')
            LIMIT 1
            """,
            (order_id,),
        ).fetchone()
    return row is not None


def record_invalid_credential_failure(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> tuple[int, bool]:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    message = "El portal rechazo la clave: clave incorrecta o cuenta no registrada."
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            INSERT INTO order_state (
                order_id, last_status, last_message, consecutive_errors,
                credential_failures, last_run_at
            ) VALUES (%s, 'error', %s, 1, 1, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                last_status = 'error',
                last_message = excluded.last_message,
                consecutive_errors = order_state.consecutive_errors + 1,
                credential_failures = order_state.credential_failures + 1,
                next_allowed_at = NULL,
                last_run_at = excluded.last_run_at
            RETURNING credential_failures
            """,
            (order_id, message, now),
        ).fetchone()
        failures = int(row["credential_failures"])
        paused = failures >= 2
        if paused:
            cursor = connection.execute(
                """
                UPDATE service_orders
                SET status = 'paused', updated_at = %s
                WHERE order_id = %s
                """,
                (now, order_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Service order not found: {order_id}")
    return failures, paused


def mark_order_done(
    order_id: str,
    *,
    status: str = "registered",
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    order_status = (
        "reserved_payment_pending" if status in {"registered", "programmed"} else "archived"
    )
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET status = %s, updated_at = %s
            WHERE order_id = %s
            """,
            (order_status, now, order_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Service order not found: {order_id}")
        if order_status == "archived":
            connection.execute(
                """
                DELETE FROM payments
                WHERE order_id = %s
                  AND status = 'pending'
                  AND EXISTS (
                      SELECT 1
                      FROM service_orders
                      WHERE service_orders.order_id = payments.order_id
                        AND service_orders.charge_required = false
                  )
                """,
                (order_id,),
            )
        connection.execute(
            """
            INSERT INTO order_state (order_id, programmed_at, last_status, last_run_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                programmed_at = excluded.programmed_at,
                last_status = excluded.last_status,
                last_run_at = excluded.last_run_at,
                next_allowed_at = NULL,
                consecutive_errors = 0
            """,
            (order_id, now, status, now),
        )


def update_order_state(
    order_id: str,
    *,
    status: str,
    message: str,
    exit_code: int,
    backoff_seconds: int | None = None,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    next_allowed_at = None
    if backoff_seconds is not None:
        next_allowed_at = (datetime.now(UTC) + timedelta(seconds=backoff_seconds)).isoformat(
            timespec="seconds"
        )
    is_error = exit_code != 0 or status in {
        ResultStatus.ERROR,
        ResultStatus.UNKNOWN,
        ResultStatus.RESERVATION_UNCONFIRMED,
    }
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO order_state (
                order_id, last_status, last_message, consecutive_errors, next_allowed_at,
                last_run_at, last_success_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                last_status = excluded.last_status,
                last_message = excluded.last_message,
                consecutive_errors = CASE
                    WHEN %s THEN order_state.consecutive_errors + 1
                    ELSE 0
                END,
                next_allowed_at = excluded.next_allowed_at,
                last_run_at = excluded.last_run_at,
                last_success_at = CASE
                    WHEN %s THEN order_state.last_success_at
                    ELSE excluded.last_success_at
                END
            """,
            (
                order_id,
                status,
                sanitize_text(message),
                1 if is_error else 0,
                next_allowed_at,
                now,
                None if is_error else now,
                is_error,
                is_error,
            ),
        )


def _order_state_row(order_id: str, *, settings: Settings | None) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        return connection.execute(
            """
            SELECT last_status, last_run_at, next_allowed_at
            FROM order_state
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()


def _set_order_submission_state(
    order_id: str,
    status: OrderStateStatus,
    message: str,
    *,
    settings: Settings | None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO order_state (order_id, last_status, last_message, last_run_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                last_status = excluded.last_status,
                last_message = excluded.last_message,
                last_run_at = excluded.last_run_at,
                next_allowed_at = NULL
            """,
            (order_id, status, message, now),
        )
