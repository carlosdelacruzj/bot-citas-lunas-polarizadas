from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from appointment_bot.config import Settings, load_settings


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


def init_database(settings: Settings | None = None) -> None:
    settings = _settings(settings)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    with _connection(settings.database_path) as connection:
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

            CREATE INDEX IF NOT EXISTS idx_clients_queue
                ON clients(active, done, priority DESC, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_runs_client_started
                ON runs(client_id, started_at DESC);
            """
        )


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
                SET next_allowed_at = NULL, consecutive_errors = 0, programmed_at = NULL
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
        "error",
        "unknown",
        "reservation_unconfirmed",
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
                message,
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
                record.message,
                record.exit_code,
                record.started_at,
                record.finished_at,
                record.duration_seconds,
                1 if record.reservation_attempted else 0,
                1 if record.reservation_confirmed else 0,
                json.dumps(record.details, ensure_ascii=False) if record.details else None,
                record.screenshot_path,
                _now(),
            ),
        )
        connection.execute("DELETE FROM run_screenshots WHERE run_id = ?", (record.run_id,))
        connection.executemany(
            "INSERT INTO run_screenshots (run_id, path, created_at) VALUES (?, ?, ?)",
            [(record.run_id, path, _now()) for path in screenshot_paths],
        )


def _settings(settings: Settings | None) -> Settings:
    return settings or load_settings(require_login=False)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
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
