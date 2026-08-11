from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, init_database


def enqueue_telegram_alert(
    *,
    dedupe_key: str,
    payload: dict[str, Any],
    settings: Settings,
) -> None:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO telegram_alert_outbox (dedupe_key, payload)
            VALUES (%s, %s)
            ON CONFLICT (dedupe_key) DO NOTHING
            """,
            (dedupe_key, Jsonb(payload)),
        )


def next_pending_telegram_alert(*, settings: Settings) -> dict[str, Any] | None:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT dedupe_key, payload, attempt_count
            FROM telegram_alert_outbox
            WHERE status = 'pending'
              AND next_attempt_at <= CURRENT_TIMESTAMP
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row is not None else None


def mark_telegram_alert_sent(
    dedupe_key: str,
    *,
    settings: Settings,
) -> None:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE telegram_alert_outbox
            SET status = 'sent', sent_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP, last_error = NULL
            WHERE dedupe_key = %s
            """,
            (dedupe_key,),
        )


def record_telegram_alert_failure(
    dedupe_key: str,
    *,
    attempt_count: int,
    max_attempts: int,
    error: str,
    settings: Settings,
) -> tuple[bool, int]:
    next_attempt_count = attempt_count + 1
    exhausted = next_attempt_count >= max_attempts
    delay_seconds = min(30, 2**next_attempt_count)
    next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE telegram_alert_outbox
            SET status = %s,
                attempt_count = %s,
                next_attempt_at = %s,
                last_error = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE dedupe_key = %s
            """,
            (
                "failed" if exhausted else "pending",
                next_attempt_count,
                next_attempt_at,
                error[:1000],
                dedupe_key,
            ),
        )
    return exhausted, delay_seconds


def telegram_alert_outbox_status(*, settings: Settings) -> dict[str, int]:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                   COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                   COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                   COALESCE(SUM(attempt_count), 0) AS attempts
            FROM telegram_alert_outbox
            """
        ).fetchone()
    return {
        "pending": int(row["pending"] or 0),
        "sent": int(row["sent"] or 0),
        "failed": int(row["failed"] or 0),
        "attempts": int(row["attempts"] or 0),
    }
