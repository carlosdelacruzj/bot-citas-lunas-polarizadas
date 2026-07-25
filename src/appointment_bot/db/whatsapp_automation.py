from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict

from psycopg.errors import UniqueViolation

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _now,
    _operation_connection,
    _settings,
    init_database,
)

WhatsAppAutomationKind = Literal["reservation_album", "post_payment_followup"]
WhatsAppAutomationStatus = Literal["sent", "failed", "uncertain"]
LEASE_SECONDS = 10 * 60


class WhatsAppAutomationJob(TypedDict):
    job_key: str
    order_id: str
    job_kind: WhatsAppAutomationKind


def enqueue_whatsapp_automation_job(
    order_id: str,
    job_kind: WhatsAppAutomationKind,
    *,
    settings: Settings | None = None,
    _connection_override=None,
) -> bool:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    now = datetime.now(UTC)
    job_key = f"{job_kind}:{order_id}"
    with _operation_connection(effective_settings, _connection_override) as connection:
        row = connection.execute(
            """
            INSERT INTO whatsapp_automation_jobs (
                job_key, order_id, job_kind, status, attempt_count,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, 'queued', 0, %s, %s)
            ON CONFLICT(job_key) DO NOTHING
            RETURNING job_key
            """,
            (job_key, order_id, job_kind, now, now),
        ).fetchone()
    return row is not None


def claim_next_whatsapp_automation_job(
    owner_token: str,
    *,
    settings: Settings,
) -> WhatsAppAutomationJob | None:
    init_database(settings)
    now = datetime.now(UTC)
    lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    try:
        with _connection(_database_url(settings)) as connection:
            row = connection.execute(
                """
                WITH candidate AS (
                    SELECT job_key
                    FROM whatsapp_automation_jobs
                    WHERE status = 'queued'
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE whatsapp_automation_jobs AS job
                SET status = 'running',
                    attempt_count = 1,
                    lease_owner = %s,
                    lease_expires_at = %s,
                    started_at = %s,
                    updated_at = %s
                FROM candidate
                WHERE job.job_key = candidate.job_key
                RETURNING job.job_key, job.order_id, job.job_kind
                """,
                (owner_token, lease_expires_at, now, now),
            ).fetchone()
    except UniqueViolation:
        return None
    if row is None:
        return None
    return {
        "job_key": str(row["job_key"]),
        "order_id": str(row["order_id"]),
        "job_kind": str(row["job_kind"]),
    }


def recover_expired_whatsapp_automation_jobs(
    *,
    settings: Settings,
) -> list[WhatsAppAutomationJob]:
    init_database(settings)
    now = datetime.now(UTC)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            UPDATE whatsapp_automation_jobs
            SET status = 'uncertain',
                lease_owner = NULL,
                lease_expires_at = NULL,
                error_message = COALESCE(
                    error_message,
                    'El proceso termino durante el intento automatico.'
                ),
                finished_at = %s,
                updated_at = %s
            WHERE status = 'running' AND lease_expires_at < %s
            RETURNING job_key, order_id, job_kind
            """,
            (now, now, now),
        ).fetchall()
    return [
        {
            "job_key": str(row["job_key"]),
            "order_id": str(row["order_id"]),
            "job_kind": str(row["job_kind"]),
        }
        for row in rows
    ]


def finish_whatsapp_automation_job(
    job_key: str,
    *,
    owner_token: str,
    status: WhatsAppAutomationStatus,
    message_id: str | None = None,
    error_message: str | None = None,
    settings: Settings,
) -> bool:
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE whatsapp_automation_jobs
            SET status = %s,
                message_id = COALESCE(%s, message_id),
                lease_owner = NULL,
                lease_expires_at = NULL,
                error_message = %s,
                finished_at = %s,
                updated_at = %s
            WHERE job_key = %s AND status = 'running' AND lease_owner = %s
            RETURNING job_key
            """,
            (
                status,
                message_id,
                error_message,
                now,
                now,
                job_key,
                owner_token,
            ),
        ).fetchone()
    return row is not None


def order_has_sent_whatsapp_message(
    order_id: str,
    job_kind: WhatsAppAutomationKind,
    *,
    settings: Settings,
) -> bool:
    init_database(settings)
    table = (
        "whatsapp_messages"
        if job_kind == "reservation_album"
        else "whatsapp_followup_messages"
    )
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            f"""
            SELECT 1
            FROM {table}
            WHERE order_id = %s AND test_mode = false AND status = 'sent'
            LIMIT 1
            """,
            (order_id,),
        ).fetchone()
    return row is not None


def whatsapp_automation_in_progress(
    order_id: str,
    job_kind: WhatsAppAutomationKind,
    *,
    settings: Settings,
) -> bool:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM whatsapp_automation_jobs
            WHERE order_id = %s
              AND job_kind = %s
              AND status IN ('queued', 'running')
            LIMIT 1
            """,
            (order_id, job_kind),
        ).fetchone()
    return row is not None


__all__ = [
    "WhatsAppAutomationJob",
    "WhatsAppAutomationKind",
    "claim_next_whatsapp_automation_job",
    "enqueue_whatsapp_automation_job",
    "finish_whatsapp_automation_job",
    "order_has_sent_whatsapp_message",
    "recover_expired_whatsapp_automation_jobs",
    "whatsapp_automation_in_progress",
]
