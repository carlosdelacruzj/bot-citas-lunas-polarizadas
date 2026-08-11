from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, init_database


def persist_captcha_shadow_event(
    *,
    event_key: str,
    event_id: str,
    sequence: int,
    endpoint: str,
    payload: dict[str, Any],
    settings: Settings,
) -> None:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO captcha_shadow_outbox (
                event_key, event_id, sequence, endpoint, payload
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (event_key) DO UPDATE SET
                endpoint = EXCLUDED.endpoint,
                payload = EXCLUDED.payload,
                status = CASE
                    WHEN captcha_shadow_outbox.payload IS DISTINCT FROM EXCLUDED.payload
                    THEN 'pending'
                    ELSE captcha_shadow_outbox.status
                END,
                next_attempt_at = CASE
                    WHEN captcha_shadow_outbox.payload IS DISTINCT FROM EXCLUDED.payload
                    THEN CURRENT_TIMESTAMP
                    ELSE captcha_shadow_outbox.next_attempt_at
                END,
                last_error = CASE
                    WHEN captcha_shadow_outbox.payload IS DISTINCT FROM EXCLUDED.payload
                    THEN NULL
                    ELSE captcha_shadow_outbox.last_error
                END,
                processed_at = CASE
                    WHEN captcha_shadow_outbox.payload IS DISTINCT FROM EXCLUDED.payload
                    THEN NULL
                    ELSE captcha_shadow_outbox.processed_at
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (event_key, event_id, sequence, endpoint, Jsonb(payload)),
        )


def next_pending_captcha_shadow_event(
    *,
    settings: Settings,
) -> dict[str, Any] | None:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT current.event_key, current.event_id, current.sequence,
                   current.endpoint, current.payload, current.attempt_count
            FROM captcha_shadow_outbox AS current
            WHERE current.status = 'pending'
              AND current.next_attempt_at <= CURRENT_TIMESTAMP
              AND NOT EXISTS (
                  SELECT 1
                  FROM captcha_shadow_outbox AS previous
                  WHERE previous.event_id = current.event_id
                    AND previous.sequence < current.sequence
                    AND previous.status <> 'processed'
              )
            ORDER BY current.created_at ASC, current.sequence ASC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row is not None else None


def mark_captcha_shadow_event_processed(
    event_key: str,
    *,
    settings: Settings,
) -> None:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE captcha_shadow_outbox
            SET status = 'processed', processed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP, last_error = NULL
            WHERE event_key = %s
            """,
            (event_key,),
        )


def mark_captcha_shadow_event_discarded(
    event_key: str,
    *,
    error: str,
    settings: Settings,
) -> None:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE captcha_shadow_outbox
            SET status = 'processed', processed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP, last_error = %s
            WHERE event_key = %s
            """,
            (f"discarded: {error}"[:1000], event_key),
        )


def defer_captcha_shadow_event(
    event_key: str,
    *,
    attempt_count: int,
    error: str,
    settings: Settings,
) -> int:
    delay_seconds = min(300, 2 ** min(max(attempt_count, 0), 8))
    next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE captcha_shadow_outbox
            SET attempt_count = attempt_count + 1,
                next_attempt_at = %s,
                last_error = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE event_key = %s
            """,
            (next_attempt_at, error[:1000], event_key),
        )
    return delay_seconds


def captcha_shadow_outbox_status(*, settings: Settings) -> dict[str, int]:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                   COUNT(*) FILTER (WHERE status = 'processed') AS processed,
                   COALESCE(SUM(attempt_count), 0) AS attempts
            FROM captcha_shadow_outbox
            """
        ).fetchone()
    return {
        "pending": int(row["pending"] or 0),
        "processed": int(row["processed"] or 0),
        "attempts": int(row["attempts"] or 0),
    }


def captcha_shadow_external_timings(
    event_ids: list[str],
    *,
    settings: Settings,
) -> dict[str, float]:
    if not event_ids:
        return {}
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT event_id,
                   MAX((payload ->> 'external_solve_ms')::double precision)
                       AS external_solve_ms
            FROM captcha_shadow_outbox
            WHERE event_id = ANY(%s)
              AND payload ? 'external_solve_ms'
            GROUP BY event_id
            """,
            (event_ids,),
        ).fetchall()
    return {
        str(row["event_id"]): float(row["external_solve_ms"])
        for row in rows
        if row["external_solve_ms"] is not None
    }


def captcha_shadow_external_timing_stats(
    event_ids: list[str],
    *,
    settings: Settings,
) -> dict[str, float | int | None]:
    if not event_ids:
        return {
            "samples": 0,
            "average": None,
            "p50": None,
            "p90": None,
        }
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            WITH event_timings AS (
                SELECT event_id,
                       MAX((payload ->> 'external_solve_ms')::double precision)
                           AS external_solve_ms
                FROM captcha_shadow_outbox
                WHERE event_id = ANY(%s)
                  AND payload ? 'external_solve_ms'
                GROUP BY event_id
            )
            SELECT COUNT(*) AS samples,
                   AVG(external_solve_ms) AS average,
                   percentile_cont(0.5) WITHIN GROUP (
                       ORDER BY external_solve_ms
                   ) AS p50,
                   percentile_cont(0.9) WITHIN GROUP (
                       ORDER BY external_solve_ms
                   ) AS p90
            FROM event_timings
            """,
            (event_ids,),
        ).fetchone()
    return {
        "samples": int(row["samples"] or 0),
        "average": _optional_float(row["average"]),
        "p50": _optional_float(row["p50"]),
        "p90": _optional_float(row["p90"]),
    }


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None
