from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, TypedDict

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _now,
    _operation_connection,
    _settings,
    init_database,
)

WhatsAppAutomationKind = Literal[
    "reservation_album",
    "post_payment_followup",
    "daily_slot_summary",
    "registration_notice",
]
RegistrationNoticeType = Literal[
    "monitoring_started",
    "no_pending_request",
    "invalid_credentials",
]
WhatsAppAutomationStatus = Literal["sent", "failed", "uncertain"]
LEASE_SECONDS = 10 * 60
PREFLIGHT_RETRY_SECONDS = 60


class WhatsAppAutomationJob(TypedDict):
    job_key: str
    order_id: str | None
    job_kind: WhatsAppAutomationKind
    report_date: str | None
    recipient_phone: str | None
    message_text: str | None
    publication_text: str | None
    attachment_paths: list[str]
    registration_notice_type: RegistrationNoticeType | None
    preflight_cycle: int | None


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
                next_attempt_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, 'queued', 0, %s, %s, %s)
            ON CONFLICT(job_key) DO NOTHING
            RETURNING job_key
            """,
            (job_key, order_id, job_kind, now, now, now),
        ).fetchone()
    return row is not None


def enqueue_daily_slot_summary_job(
    *,
    report_date: date,
    recipient_phone: str,
    message_text: str,
    publication_text: str,
    attachment_paths: list[Path],
    retry_sequence: int | None = None,
    settings: Settings | None = None,
    _connection_override=None,
) -> bool:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    now = datetime.now(UTC)
    job_key = f"daily_slot_summary:{report_date.isoformat()}"
    if retry_sequence is not None:
        if retry_sequence < 1:
            raise ValueError("retry_sequence must be greater than or equal to 1.")
        job_key = f"{job_key}:retry-{retry_sequence}"
    phone = _international_phone(recipient_phone)
    paths = [str(path.resolve()) for path in attachment_paths]
    with _operation_connection(effective_settings, _connection_override) as connection:
        row = connection.execute(
            """
            INSERT INTO whatsapp_automation_jobs (
                job_key, order_id, job_kind, report_date, recipient_phone,
                message_text, publication_text, attachment_paths, status, attempt_count,
                next_attempt_at, created_at, updated_at
            )
            VALUES (
                %s, NULL, 'daily_slot_summary', %s, %s,
                %s, %s, %s, 'queued', 0, %s, %s, %s
            )
            ON CONFLICT(job_key) DO NOTHING
            RETURNING job_key
            """,
            (
                job_key,
                report_date,
                phone,
                message_text,
                publication_text,
                Jsonb(paths),
                now,
                now,
                now,
            ),
        ).fetchone()
    return row is not None


def enqueue_registration_notice_job(
    *,
    order_id: str,
    preflight_cycle: int,
    notice_type: RegistrationNoticeType,
    recipient_phone: str,
    message_text: str,
    settings: Settings | None = None,
    _connection_override=None,
) -> bool:
    if preflight_cycle < 1:
        raise ValueError("preflight_cycle must be greater than or equal to 1.")
    effective_settings = _settings(settings)
    init_database(effective_settings)
    now = datetime.now(UTC)
    job_key = f"registration_notice:{order_id}:cycle-{preflight_cycle}:{notice_type}"
    phone = _international_phone(recipient_phone)
    with _operation_connection(effective_settings, _connection_override) as connection:
        row = connection.execute(
            """
            INSERT INTO whatsapp_automation_jobs (
                job_key, order_id, job_kind, recipient_phone, message_text,
                registration_notice_type, preflight_cycle, status, attempt_count,
                next_attempt_at, created_at, updated_at
            )
            VALUES (
                %s, %s, 'registration_notice', %s, %s,
                %s, %s, 'queued', 0, %s, %s, %s
            )
            ON CONFLICT(job_key) DO NOTHING
            RETURNING job_key
            """,
            (
                job_key,
                order_id,
                phone,
                message_text,
                notice_type,
                preflight_cycle,
                now,
                now,
                now,
            ),
        ).fetchone()
    return row is not None


def next_waiting_whatsapp_automation_job(
    *,
    settings: Settings,
) -> WhatsAppAutomationJob | None:
    init_database(settings)
    now = datetime.now(UTC)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT job_key, order_id, job_kind, report_date, recipient_phone,
                   message_text, publication_text, attachment_paths,
                   registration_notice_type, preflight_cycle
            FROM whatsapp_automation_jobs
            WHERE status IN ('queued', 'blocked') AND next_attempt_at <= %s
            ORDER BY created_at
            LIMIT 1
            """,
            (now,),
        ).fetchone()
    if row is None:
        return None
    return _job_from_row(row)


def claim_whatsapp_automation_job(
    job_key: str,
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
                UPDATE whatsapp_automation_jobs
                SET status = 'running',
                    attempt_count = 1,
                    lease_owner = %s,
                    lease_expires_at = %s,
                    started_at = %s,
                    preflight_error = NULL,
                    updated_at = %s
                WHERE job_key = %s
                  AND status IN ('queued', 'blocked')
                  AND next_attempt_at <= %s
                RETURNING job_key, order_id, job_kind, report_date, recipient_phone,
                          message_text, publication_text, attachment_paths,
                          registration_notice_type, preflight_cycle
                """,
                (owner_token, lease_expires_at, now, now, job_key, now),
            ).fetchone()
    except UniqueViolation:
        return None
    if row is None:
        return None
    return _job_from_row(row)


def block_whatsapp_automation_preflight(
    job_key: str,
    *,
    error_message: str,
    settings: Settings,
) -> bool:
    init_database(settings)
    now = datetime.now(UTC)
    next_attempt_at = now + timedelta(seconds=PREFLIGHT_RETRY_SECONDS)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE whatsapp_automation_jobs
            SET status = 'blocked',
                next_attempt_at = %s,
                preflight_error = %s,
                preflight_alerted_at = CASE
                    WHEN preflight_error IS DISTINCT FROM %s
                      OR preflight_alerted_at IS NULL
                    THEN %s
                    ELSE preflight_alerted_at
                END,
                updated_at = %s
            WHERE job_key = %s
              AND status IN ('queued', 'blocked')
              AND attempt_count = 0
            RETURNING (
                preflight_alerted_at = %s
            ) AS should_alert
            """,
            (
                next_attempt_at,
                error_message,
                error_message,
                now,
                now,
                job_key,
                now,
            ),
        ).fetchone()
    return bool(row and row["should_alert"])


def return_running_whatsapp_job_to_blocked(
    job_key: str,
    *,
    owner_token: str,
    error_message: str,
    settings: Settings,
) -> bool:
    init_database(settings)
    now = datetime.now(UTC)
    next_attempt_at = now + timedelta(seconds=PREFLIGHT_RETRY_SECONDS)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE whatsapp_automation_jobs
            SET status = 'blocked',
                attempt_count = 0,
                lease_owner = NULL,
                lease_expires_at = NULL,
                started_at = NULL,
                next_attempt_at = %s,
                preflight_error = %s,
                preflight_alerted_at = %s,
                updated_at = %s
            WHERE job_key = %s AND status = 'running' AND lease_owner = %s
            RETURNING job_key
            """,
            (
                next_attempt_at,
                error_message,
                now,
                now,
                job_key,
                owner_token,
            ),
        ).fetchone()
    return row is not None


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
            RETURNING job_key, order_id, job_kind, report_date, recipient_phone,
                      message_text, publication_text, attachment_paths,
                      registration_notice_type, preflight_cycle
            """,
            (now, now, now),
        ).fetchall()
    return [_job_from_row(row) for row in rows]


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
              AND status IN ('queued', 'blocked', 'running')
            LIMIT 1
            """,
            (order_id, job_kind),
        ).fetchone()
    return row is not None


def _job_from_row(row) -> WhatsAppAutomationJob:
    raw_paths = row["attachment_paths"]
    return {
        "job_key": str(row["job_key"]),
        "order_id": str(row["order_id"]) if row["order_id"] is not None else None,
        "job_kind": str(row["job_kind"]),
        "report_date": (
            str(row["report_date"]) if row["report_date"] is not None else None
        ),
        "recipient_phone": (
            str(row["recipient_phone"]) if row["recipient_phone"] is not None else None
        ),
        "message_text": (
            str(row["message_text"]) if row["message_text"] is not None else None
        ),
        "publication_text": (
            str(row["publication_text"])
            if row["publication_text"] is not None
            else None
        ),
        "attachment_paths": (
            [str(path) for path in raw_paths] if isinstance(raw_paths, list) else []
        ),
        "registration_notice_type": (
            str(row["registration_notice_type"])
            if row["registration_notice_type"] is not None
            else None
        ),
        "preflight_cycle": (
            int(row["preflight_cycle"])
            if row["preflight_cycle"] is not None
            else None
        ),
    }


def _international_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("El WhatsApp debe incluir codigo de pais y entre 10 y 15 digitos.")
    return f"+{digits}"


__all__ = [
    "WhatsAppAutomationJob",
    "WhatsAppAutomationKind",
    "block_whatsapp_automation_preflight",
    "claim_whatsapp_automation_job",
    "enqueue_daily_slot_summary_job",
    "enqueue_registration_notice_job",
    "enqueue_whatsapp_automation_job",
    "finish_whatsapp_automation_job",
    "next_waiting_whatsapp_automation_job",
    "order_has_sent_whatsapp_message",
    "recover_expired_whatsapp_automation_jobs",
    "return_running_whatsapp_job_to_blocked",
    "whatsapp_automation_in_progress",
]
