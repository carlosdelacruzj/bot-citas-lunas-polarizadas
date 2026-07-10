from __future__ import annotations

from typing import Any

from appointment_bot.config import Settings
from appointment_bot.core.models import WorkerState
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _now,
    _settings,
    _timestamp_text,
    init_database,
)


def get_worker_state(settings: Settings | None = None) -> WorkerState:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT phase, paused, current_order_id, masked_account,
                   session_started_at, last_check_at, next_check_at,
                   confirmed_reservations, consecutive_errors, last_error,
                   availability_signature, owner_token, updated_at
            FROM worker_state
            WHERE id = 1
            """
        ).fetchone()
    if row is None:
        return WorkerState()
    return WorkerState(
        phase=str(row["phase"]),
        paused=bool(row["paused"]),
        current_order_id=row["current_order_id"],
        masked_account=row["masked_account"],
        session_started_at=_timestamp_text(row["session_started_at"]),
        last_check_at=_timestamp_text(row["last_check_at"]),
        next_check_at=_timestamp_text(row["next_check_at"]),
        confirmed_reservations=int(row["confirmed_reservations"]),
        consecutive_errors=int(row["consecutive_errors"]),
        last_error=row["last_error"],
        availability_signature=row["availability_signature"],
        owner_token=row["owner_token"],
        updated_at=_timestamp_text(row["updated_at"]),
    )


def acquire_worker_lease(
    owner_token: str,
    *,
    lease_seconds: int,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE worker_state
            SET owner_token = %s,
                lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
              AND (
                  owner_token IS NULL
                  OR owner_token = %s
                  OR lease_expires_at IS NULL
                  OR lease_expires_at <= CURRENT_TIMESTAMP
              )
            """,
            (owner_token, lease_seconds, owner_token),
        )
        return bool(cursor.rowcount)


def renew_worker_lease(
    owner_token: str,
    *,
    lease_seconds: int,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE worker_state
            SET lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
              AND owner_token = %s
              AND lease_expires_at > CURRENT_TIMESTAMP
            """,
            (lease_seconds, owner_token),
        )
        return bool(cursor.rowcount)


def release_worker_lease(
    owner_token: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE worker_state
            SET owner_token = NULL,
                lease_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1 AND owner_token = %s
            """,
            (owner_token,),
        )


def update_worker_state(
    settings: Settings | None = None,
    *,
    expected_owner_token: str | None = None,
    **changes: Any,
) -> WorkerState:
    settings = _settings(settings)
    init_database(settings)
    allowed = {
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
        "availability_signature",
        "owner_token",
    }
    invalid = set(changes) - allowed
    if invalid:
        raise ValueError(f"Invalid worker state fields: {sorted(invalid)}")
    if not changes:
        return get_worker_state(settings)

    assignments = []
    values = []
    for key, value in changes.items():
        assignments.append(f"{key} = %s")
        values.append(value)
    assignments.append("updated_at = %s")
    values.append(_now())
    values.append(1)
    where = "id = %s"
    if expected_owner_token is not None:
        where += " AND owner_token = %s"
        values.append(expected_owner_token)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            f"UPDATE worker_state SET {', '.join(assignments)} WHERE {where}",
            values,
        )
        if expected_owner_token is not None and cursor.rowcount != 1:
            raise RuntimeError("Worker state ownership changed during the update.")
    return get_worker_state(settings)
