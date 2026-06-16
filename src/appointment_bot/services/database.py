from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from appointment_bot.config import Settings, load_settings
from appointment_bot.domain import (
    ClientStateStatus,
    ResultStatus,
    sanitize_details,
)
from appointment_bot.utils.sanitization import sanitize_text

_INITIALIZED_PATHS: set[Path] = set()
_INITIALIZATION_LOCK = threading.Lock()
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Client:
    client_id: str
    name: str
    username: str
    password: str
    priority: int
    active: bool
    done: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    client_id: str | None
    status: str
    message: str
    exit_code: int
    started_at: str
    finished_at: str
    duration_seconds: float
    reservation_attempted: bool
    reservation_confirmed: bool
    details: dict[str, Any] | None
    screenshot_path: str | None


@dataclass(frozen=True)
class WorkerState:
    phase: str = "stopped"
    paused: bool = False
    current_client_id: str | None = None
    masked_account: str | None = None
    session_started_at: str | None = None
    last_check_at: str | None = None
    next_check_at: str | None = None
    confirmed_reservations: int = 0
    consecutive_errors: int = 0
    last_error: str | None = None
    availability_signature: str | None = None
    owner_token: str | None = None
    updated_at: str | None = None


def init_database(settings: Settings | None = None) -> None:
    settings = _settings(settings)
    database_path = settings.database_path.resolve()
    if database_path in _INITIALIZED_PATHS:
        return

    with _INITIALIZATION_LOCK:
        if database_path in _INITIALIZED_PATHS:
            return
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with _connection(database_path) as connection:
            connection.executescript(
                """
            CREATE TABLE IF NOT EXISTS clients (
                client_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS client_state (
                client_id TEXT PRIMARY KEY REFERENCES clients(client_id) ON DELETE CASCADE,
                last_status TEXT,
                last_message TEXT,
                consecutive_errors INTEGER NOT NULL DEFAULT 0,
                next_allowed_at TEXT,
                last_run_at TEXT,
                last_success_at TEXT,
                programmed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                client_id TEXT REFERENCES clients(client_id) ON DELETE SET NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                exit_code INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                reservation_attempted INTEGER NOT NULL DEFAULT 0,
                reservation_confirmed INTEGER NOT NULL DEFAULT 0,
                details_json TEXT,
                screenshot_path TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS run_screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS worker_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                phase TEXT NOT NULL DEFAULT 'stopped',
                paused INTEGER NOT NULL DEFAULT 0,
                current_client_id TEXT,
                masked_account TEXT,
                session_started_at TEXT,
                last_check_at TEXT,
                next_check_at TEXT,
                confirmed_reservations INTEGER NOT NULL DEFAULT 0,
                consecutive_errors INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                availability_signature TEXT,
                owner_token TEXT,
                updated_at TEXT NOT NULL
            );

            INSERT OR IGNORE INTO worker_state (id, updated_at)
            VALUES (1, CURRENT_TIMESTAMP);

            CREATE INDEX IF NOT EXISTS idx_clients_queue
                ON clients(active, done, priority DESC, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_runs_client_started
                ON runs(client_id, started_at DESC);
            """
            )
            _migrate_database(connection)
        _INITIALIZED_PATHS.add(database_path)


def add_client(
    client_id: str,
    name: str,
    username: str,
    password: str,
    priority: int,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO clients (
                client_id, name, username, password, priority, active, done, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 1, 0, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                name = excluded.name,
                username = excluded.username,
                password = excluded.password,
                priority = excluded.priority,
                active = 1,
                done = 0,
                updated_at = excluded.updated_at
            """,
            (client_id, name, username, password, priority, now, now),
        )
        connection.execute(
            "INSERT OR IGNORE INTO client_state (client_id) VALUES (?)",
            (client_id,),
        )
        connection.execute(
            """
            UPDATE client_state
            SET last_status = NULL,
                last_message = NULL,
                consecutive_errors = 0,
                next_allowed_at = NULL,
                programmed_at = NULL
            WHERE client_id = ?
            """,
            (client_id,),
        )


def list_clients(settings: Settings | None = None) -> list[Client]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        rows = connection.execute(
            """
            SELECT client_id, name, username, password, priority, active, done,
                   created_at, updated_at
            FROM clients
            ORDER BY priority DESC, created_at ASC
            """
        ).fetchall()
    return [_client_from_row(row) for row in rows]


def get_client(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> Client | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        row = connection.execute(
            """
            SELECT client_id, name, username, password, priority, active, done,
                   created_at, updated_at
            FROM clients
            WHERE client_id = ?
            """,
            (client_id,),
        ).fetchone()
    return _client_from_row(row) if row is not None else None


def list_active_clients(settings: Settings | None = None) -> list[Client]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        rows = connection.execute(
            """
            SELECT c.client_id, c.name, c.username, c.password, c.priority,
                   c.active, c.done, c.created_at, c.updated_at
            FROM clients c
            WHERE c.active = 1
              AND c.done = 0
            ORDER BY c.priority DESC, c.created_at ASC
            """
        ).fetchall()
    return [_client_from_row(row) for row in rows]


def client_backoff_seconds(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> int:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        row = connection.execute(
            "SELECT next_allowed_at FROM client_state WHERE client_id = ?",
            (client_id,),
        ).fetchone()

    if row is None or not row["next_allowed_at"]:
        return 0

    try:
        next_allowed_at = datetime.fromisoformat(str(row["next_allowed_at"]))
    except ValueError:
        return 0
    return max(0, int((next_allowed_at - datetime.now()).total_seconds()))


def client_reservation_pending(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        row = connection.execute(
            "SELECT last_status FROM client_state WHERE client_id = ?",
            (client_id,),
        ).fetchone()
    return row is not None and row["last_status"] in {
        ClientStateStatus.SUBMISSION_INTENT,
        ClientStateStatus.SUBMISSION_PENDING,
        ClientStateStatus.RESERVATION_UNCONFIRMED,
    }


def mark_client_submission_pending(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO client_state (client_id, last_status, last_message, last_run_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                last_status = excluded.last_status,
                last_message = excluded.last_message,
                last_run_at = excluded.last_run_at,
                next_allowed_at = NULL
            """,
            (
                client_id,
                ClientStateStatus.SUBMISSION_PENDING,
                "Se inicio el envio de una reserva; falta confirmar el resultado.",
                now,
            ),
        )


def mark_client_submission_intent(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    _set_client_submission_state(
        client_id,
        ClientStateStatus.SUBMISSION_INTENT,
        "Se iniciara el click de reserva; todavia no se confirma su envio.",
        settings=settings,
    )


def clear_client_submission_state(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        connection.execute(
            """
            UPDATE client_state
            SET last_status = NULL,
                last_message = NULL,
                next_allowed_at = NULL
            WHERE client_id = ?
              AND last_status IN (?, ?, ?)
            """,
            (
                client_id,
                ClientStateStatus.SUBMISSION_INTENT,
                ClientStateStatus.SUBMISSION_PENDING,
                ClientStateStatus.RESERVATION_UNCONFIRMED,
            ),
        )


def client_submission_age_seconds(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> int | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        row = connection.execute(
            """
            SELECT last_status, last_run_at
            FROM client_state
            WHERE client_id = ?
            """,
            (client_id,),
        ).fetchone()
    if row is None or row["last_status"] not in {
        ClientStateStatus.SUBMISSION_INTENT,
        ClientStateStatus.SUBMISSION_PENDING,
        ClientStateStatus.RESERVATION_UNCONFIRMED,
    }:
        return None
    try:
        started_at = datetime.fromisoformat(str(row["last_run_at"]))
    except (TypeError, ValueError):
        return None
    return max(0, int((datetime.now() - started_at).total_seconds()))


def set_client_active(client_id: str, active: bool, *, settings: Settings | None = None) -> None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        now = _now()
        if active:
            connection.execute(
                "UPDATE clients SET active = 1, done = 0, updated_at = ? WHERE client_id = ?",
                (now, client_id),
            )
            connection.execute(
                """
                UPDATE client_state
                SET last_status = NULL,
                    last_message = NULL,
                    next_allowed_at = NULL,
                    consecutive_errors = 0,
                    programmed_at = NULL
                WHERE client_id = ?
                """,
                (client_id,),
            )
        else:
            connection.execute(
                "UPDATE clients SET active = 0, updated_at = ? WHERE client_id = ?",
                (now, client_id),
            )


def mark_client_done(
    client_id: str,
    *,
    status: str = "registered",
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(settings.database_path) as connection:
        connection.execute(
            "UPDATE clients SET done = 1, active = 0, updated_at = ? WHERE client_id = ?",
            (now, client_id),
        )
        connection.execute(
            """
            INSERT INTO client_state (client_id, programmed_at, last_status, last_run_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                programmed_at = excluded.programmed_at,
                last_status = excluded.last_status,
                last_run_at = excluded.last_run_at,
                next_allowed_at = NULL,
                consecutive_errors = 0
            """,
            (client_id, now, status, now),
        )


def update_client_state(
    client_id: str,
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
        next_allowed_at = (datetime.now() + timedelta(seconds=backoff_seconds)).isoformat(
            timespec="seconds"
        )
    is_error = exit_code != 0 or status in {
        ResultStatus.ERROR,
        ResultStatus.UNKNOWN,
        ResultStatus.RESERVATION_UNCONFIRMED,
    }
    with _connection(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO client_state (
                client_id, last_status, last_message, consecutive_errors, next_allowed_at,
                last_run_at, last_success_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                last_status = excluded.last_status,
                last_message = excluded.last_message,
                consecutive_errors = CASE
                    WHEN ? THEN client_state.consecutive_errors + 1
                    ELSE 0
                END,
                next_allowed_at = excluded.next_allowed_at,
                last_run_at = excluded.last_run_at,
                last_success_at = CASE
                    WHEN ? THEN client_state.last_success_at
                    ELSE excluded.last_success_at
                END
            """,
            (
                client_id,
                status,
                sanitize_text(message),
                1 if is_error else 0,
                next_allowed_at,
                now,
                None if is_error else now,
                1 if is_error else 0,
                1 if is_error else 0,
            ),
        )


def create_run_record(
    settings: Settings | None,
    record: RunRecord,
    screenshot_paths: Iterable[str],
) -> None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, client_id, status, message, exit_code, started_at, finished_at,
                duration_seconds, reservation_attempted, reservation_confirmed, details_json,
                screenshot_path, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run_id,
                record.client_id,
                record.status,
                sanitize_text(record.message),
                record.exit_code,
                record.started_at,
                record.finished_at,
                record.duration_seconds,
                1 if record.reservation_attempted else 0,
                1 if record.reservation_confirmed else 0,
                (
                    json.dumps(sanitize_details(record.details), ensure_ascii=False)
                    if record.details
                    else None
                ),
                record.screenshot_path,
                _now(),
            ),
        )
        connection.execute("DELETE FROM run_screenshots WHERE run_id = ?", (record.run_id,))
        connection.executemany(
            "INSERT INTO run_screenshots (run_id, path, created_at) VALUES (?, ?, ?)",
            [(record.run_id, path, _now()) for path in screenshot_paths],
        )


def get_worker_state(settings: Settings | None = None) -> WorkerState:
    settings = _settings(settings)
    init_database(settings)
    with _connection(settings.database_path) as connection:
        row = connection.execute(
            """
            SELECT phase, paused, current_client_id, masked_account,
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
        current_client_id=row["current_client_id"],
        masked_account=row["masked_account"],
        session_started_at=row["session_started_at"],
        last_check_at=row["last_check_at"],
        next_check_at=row["next_check_at"],
        confirmed_reservations=int(row["confirmed_reservations"]),
        consecutive_errors=int(row["consecutive_errors"]),
        last_error=row["last_error"],
        availability_signature=row["availability_signature"],
        owner_token=row["owner_token"],
        updated_at=row["updated_at"],
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
        "current_client_id",
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
        assignments.append(f"{key} = ?")
        values.append(1 if key == "paused" and value else 0 if key == "paused" else value)
    assignments.append("updated_at = ?")
    values.append(_now())
    values.append(1)
    where = "id = ?"
    if expected_owner_token is not None:
        where += " AND owner_token = ?"
        values.append(expected_owner_token)
    with _connection(settings.database_path) as connection:
        cursor = connection.execute(
            f"UPDATE worker_state SET {', '.join(assignments)} WHERE {where}",
            values,
        )
        if expected_owner_token is not None and cursor.rowcount != 1:
            raise RuntimeError("Worker state ownership changed during the update.")
    return get_worker_state(settings)


def cleanup_database_history(
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    cutoff = (datetime.now() - timedelta(days=settings.cleanup_retention_days)).isoformat(
        timespec="seconds"
    )
    with _connection(settings.database_path) as connection:
        connection.execute("DELETE FROM runs WHERE created_at < ?", (cutoff,))
        connection.execute(
            """
            DELETE FROM run_screenshots
            WHERE run_id NOT IN (SELECT run_id FROM runs)
            """
        )


def _settings(settings: Settings | None) -> Settings:
    return settings or load_settings(require_login=False)


def _set_client_submission_state(
    client_id: str,
    status: ClientStateStatus,
    message: str,
    *,
    settings: Settings | None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO client_state (client_id, last_status, last_message, last_run_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                last_status = excluded.last_status,
                last_message = excluded.last_message,
                last_run_at = excluded.last_run_at,
                next_allowed_at = NULL
            """,
            (client_id, status, message, now),
        )


def _migrate_database(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version < 1:
        version = 1
    if version < 2:
        worker_columns = {
            str(row["name"]) for row in connection.execute("PRAGMA table_info(worker_state)")
        }
        if "owner_token" not in worker_columns:
            connection.execute("ALTER TABLE worker_state ADD COLUMN owner_token TEXT")
        version = 2
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def _connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = _connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _client_from_row(row: sqlite3.Row) -> Client:
    return Client(
        client_id=str(row["client_id"]),
        name=str(row["name"]),
        username=str(row["username"]),
        password=str(row["password"]),
        priority=int(row["priority"]),
        active=bool(row["active"]),
        done=bool(row["done"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
