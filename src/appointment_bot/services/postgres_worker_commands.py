from __future__ import annotations

from typing import Any
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.services.database_models import WorkerCommand
from appointment_bot.services.postgres_common import (
    _connection,
    _database_url,
    _settings,
    _timestamp_text,
    init_database,
)

VALID_WORKER_COMMANDS = {"pause", "resume", "restart"}


def enqueue_worker_command(
    command: str,
    *,
    requested_by: str | None = None,
    settings: Settings | None = None,
) -> WorkerCommand:
    command = command.strip().lower()
    if command not in VALID_WORKER_COMMANDS:
        raise ValueError(f"Unsupported worker command: {command}")
    settings = _settings(settings)
    init_database(settings)
    command_id = f"worker-command-{uuid4().hex}"
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            INSERT INTO worker_commands (
                command_id, command, status, requested_by, requested_at
            )
            VALUES (%s, %s, 'pending', %s, CURRENT_TIMESTAMP)
            RETURNING command_id, command, status, requested_by, worker_owner_token,
                      requested_at, claimed_at, processed_at, error_message
            """,
            (command_id, command, requested_by),
        ).fetchone()
    return _worker_command(row)


def claim_next_worker_command(
    *,
    owner_token: str,
    settings: Settings | None = None,
) -> WorkerCommand | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE worker_commands
            SET status = 'processing',
                worker_owner_token = %s,
                claimed_at = CURRENT_TIMESTAMP
            WHERE command_id = (
                SELECT command_id
                FROM worker_commands
                WHERE status = 'pending'
                ORDER BY requested_at ASC, command_id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING command_id, command, status, requested_by, worker_owner_token,
                      requested_at, claimed_at, processed_at, error_message
            """,
            (owner_token,),
        ).fetchone()
    return _worker_command(row) if row is not None else None


def complete_worker_command(
    command_id: str,
    *,
    status: str,
    error_message: str | None = None,
    settings: Settings | None = None,
) -> None:
    if status not in {"applied", "failed"}:
        raise ValueError(f"Unsupported worker command completion status: {status}")
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE worker_commands
            SET status = %s,
                processed_at = CURRENT_TIMESTAMP,
                error_message = %s
            WHERE command_id = %s
            """,
            (status, error_message, command_id),
        )


def _worker_command(row: Any) -> WorkerCommand:
    return WorkerCommand(
        command_id=str(row["command_id"]),
        command=str(row["command"]),
        status=str(row["status"]),
        requested_by=row["requested_by"],
        worker_owner_token=row["worker_owner_token"],
        requested_at=_timestamp_text(row["requested_at"]) or "",
        claimed_at=_timestamp_text(row["claimed_at"]),
        processed_at=_timestamp_text(row["processed_at"]),
        error_message=row["error_message"],
    )
