from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, TypedDict

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.core.contacts import (
    normalize_contact_whatsapp,
    resolve_whatsapp_recipient,
)
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _now,
    _operation_connection,
    _settings,
    init_database,
)
from appointment_bot.utils.sanitization import sanitize_text

WhatsAppAutomationKind = Literal[
    "reservation_album",
    "post_payment_followup",
    "daily_slot_summary",
    "registration_notice",
    "appointment_reminder",
]
RegistrationNoticeType = Literal[
    "monitoring_started",
    "no_pending_request",
    "invalid_credentials",
]
WhatsAppAutomationStatus = Literal["sent", "failed", "uncertain", "skipped"]
LEASE_SECONDS = 10 * 60
PREFLIGHT_RETRY_SECONDS = 60
WHATSAPP_REVIEW_RESOLUTIONS = {
    "confirmed_complete",
    "completed_missing",
    "dismissed",
}


class WhatsAppAutomationJob(TypedDict):
    job_key: str
    order_id: str | None
    reservation_id: str | None
    job_kind: WhatsAppAutomationKind
    report_date: str | None
    appointment_day: str | None
    recipient_phone: str | None
    recipient_username: str | None
    message_text: str | None
    publication_text: str | None
    attachment_paths: list[str]
    registration_notice_type: RegistrationNoticeType | None
    preflight_cycle: int | None
    template_key: str | None
    template_revision: int | None


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
                priority, next_attempt_at, created_at, updated_at
            )
            VALUES (
                %s, NULL, 'daily_slot_summary', %s, %s,
                %s, %s, %s, 'queued', 0, 0, %s, %s, %s
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


def enqueue_appointment_reminder_job(
    *,
    service_date: date,
    appointment_day: date,
    reservation_id: str,
    order_id: str,
    recipient_phone: str | None,
    recipient_username: str | None,
    message_text: str,
    template_key: str,
    template_revision: int,
    settings: Settings | None = None,
    _connection_override=None,
) -> bool:
    if not template_key.strip() or template_revision < 1:
        raise ValueError("Appointment reminder template trace is invalid.")
    effective_settings = _settings(settings)
    init_database(effective_settings)
    now = datetime.now(UTC)
    phone, username = resolve_whatsapp_recipient(recipient_phone, recipient_username)
    if phone is not None:
        phone = _international_phone(phone)
    job_key = f"appointment_reminder:{reservation_id}:{appointment_day.isoformat()}"
    with _operation_connection(effective_settings, _connection_override) as connection:
        row = connection.execute(
            """
            INSERT INTO whatsapp_automation_jobs (
                job_key, order_id, reservation_id, job_kind, report_date,
                appointment_day, recipient_phone, recipient_username, message_text,
                template_key, template_revision, status, attempt_count, priority,
                next_attempt_at, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, 'appointment_reminder', %s,
                %s, %s, %s, %s,
                %s, %s, 'blocked', 0, 100, %s, %s, %s
            )
            ON CONFLICT(job_key) DO NOTHING
            RETURNING job_key
            """,
            (
                job_key,
                order_id,
                reservation_id,
                service_date,
                appointment_day,
                phone,
                username,
                message_text,
                template_key.strip(),
                template_revision,
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
    recipient_phone: str | None,
    recipient_username: str | None,
    message_text: str,
    template_key: str | None = None,
    template_revision: int | None = None,
    settings: Settings | None = None,
    _connection_override=None,
) -> bool:
    if preflight_cycle < 1:
        raise ValueError("preflight_cycle must be greater than or equal to 1.")
    if (template_key is None) != (template_revision is None):
        raise ValueError("template_key and template_revision must be provided together.")
    if template_revision is not None and template_revision < 1:
        raise ValueError("template_revision must be greater than or equal to 1.")
    effective_settings = _settings(settings)
    init_database(effective_settings)
    now = datetime.now(UTC)
    job_key = f"registration_notice:{order_id}:cycle-{preflight_cycle}:{notice_type}"
    phone, username = resolve_whatsapp_recipient(recipient_phone, recipient_username)
    if phone is not None:
        phone = _international_phone(phone)
    with _operation_connection(effective_settings, _connection_override) as connection:
        row = connection.execute(
            """
            INSERT INTO whatsapp_automation_jobs (
                job_key, order_id, job_kind, recipient_phone, recipient_username, message_text,
                registration_notice_type, preflight_cycle, template_key,
                template_revision, status, attempt_count,
                next_attempt_at, created_at, updated_at
            )
            VALUES (
                %s, %s, 'registration_notice', %s, %s, %s,
                %s, %s, %s, %s, 'queued', 0, %s, %s, %s
            )
            ON CONFLICT(job_key) DO NOTHING
            RETURNING job_key
            """,
            (
                job_key,
                order_id,
                phone,
                username,
                message_text,
                notice_type,
                preflight_cycle,
                template_key,
                template_revision,
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
            SELECT job_key, order_id, reservation_id, job_kind, report_date,
                   appointment_day, recipient_phone,
                   recipient_username,
                   message_text, publication_text, attachment_paths,
                   registration_notice_type, preflight_cycle,
                   template_key, template_revision
            FROM whatsapp_automation_jobs
            WHERE status IN ('queued', 'blocked') AND next_attempt_at <= %s
              AND (
                    job_kind <> 'appointment_reminder'
                    OR EXISTS (
                        SELECT 1 FROM appointment_reminder_control arc
                        WHERE arc.id = 1
                          AND arc.mode = 'live'
                    )
              )
              AND (
                    job_kind <> 'appointment_reminder'
                    OR (
                        EXISTS (
                            SELECT 1
                            FROM whatsapp_automation_jobs summary_job
                            WHERE summary_job.job_kind = 'daily_slot_summary'
                              AND summary_job.report_date = whatsapp_automation_jobs.report_date
                        )
                        AND NOT EXISTS (
                            SELECT 1
                            FROM whatsapp_automation_jobs active_summary
                            WHERE active_summary.job_kind = 'daily_slot_summary'
                              AND active_summary.report_date = whatsapp_automation_jobs.report_date
                              AND active_summary.status IN ('queued', 'blocked', 'running')
                        )
                    )
              )
            ORDER BY priority, created_at
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
                  AND (
                        job_kind <> 'appointment_reminder'
                        OR EXISTS (
                            SELECT 1 FROM appointment_reminder_control arc
                            WHERE arc.id = 1
                              AND arc.mode = 'live'
                        )
                  )
                  AND (
                        job_kind <> 'appointment_reminder'
                        OR (
                            EXISTS (
                                SELECT 1
                                FROM whatsapp_automation_jobs summary_job
                                WHERE summary_job.job_kind = 'daily_slot_summary'
                                  AND summary_job.report_date = whatsapp_automation_jobs.report_date
                            )
                            AND NOT EXISTS (
                                SELECT 1
                                FROM whatsapp_automation_jobs active_summary
                                WHERE active_summary.job_kind = 'daily_slot_summary'
                                  AND active_summary.report_date =
                                      whatsapp_automation_jobs.report_date
                                  AND active_summary.status IN ('queued', 'blocked', 'running')
                            )
                        )
                  )
                RETURNING job_key, order_id, reservation_id, job_kind, report_date,
                          appointment_day, recipient_phone,
                          recipient_username,
                          message_text, publication_text, attachment_paths,
                          registration_notice_type, preflight_cycle,
                          template_key, template_revision
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
            RETURNING job_key, order_id, reservation_id, job_kind, report_date,
                      appointment_day, recipient_phone,
                      recipient_username,
                      message_text, publication_text, attachment_paths,
                      registration_notice_type, preflight_cycle,
                      template_key, template_revision
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


def refresh_running_appointment_reminder_snapshot(
    job_key: str,
    *,
    owner_token: str,
    recipient_phone: str | None,
    recipient_username: str | None,
    message_text: str,
    template_key: str,
    template_revision: int,
    settings: Settings,
) -> WhatsAppAutomationJob | None:
    if not template_key.strip() or template_revision < 1:
        raise ValueError("Appointment reminder template trace is invalid.")
    init_database(settings)
    phone, username = resolve_whatsapp_recipient(recipient_phone, recipient_username)
    if phone is not None:
        phone = _international_phone(phone)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE whatsapp_automation_jobs
            SET recipient_phone = %s,
                recipient_username = %s,
                message_text = %s,
                template_key = %s,
                template_revision = %s,
                updated_at = %s
            WHERE job_key = %s
              AND job_kind = 'appointment_reminder'
              AND status = 'running'
              AND lease_owner = %s
            RETURNING job_key, order_id, reservation_id, job_kind, report_date,
                      appointment_day, recipient_phone, recipient_username,
                      message_text, publication_text, attachment_paths,
                      registration_notice_type, preflight_cycle,
                      template_key, template_revision
            """,
            (
                phone,
                username,
                message_text,
                template_key.strip(),
                template_revision,
                now,
                job_key,
                owner_token,
            ),
        ).fetchone()
    return _job_from_row(row) if row is not None else None


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


def get_order_whatsapp_review(
    order_id: str,
    job_kind: WhatsAppAutomationKind,
    *,
    settings: Settings | None = None,
) -> dict[str, object]:
    if job_kind not in {"reservation_album", "post_payment_followup"}:
        raise ValueError("Unsupported WhatsApp review kind.")
    effective_settings = _settings(settings)
    init_database(effective_settings)
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            """
            SELECT jobs.job_key, jobs.order_id, jobs.job_kind, jobs.status,
                   jobs.message_id, jobs.error_message, jobs.review_resolution,
                   jobs.review_note, jobs.reviewed_at, jobs.reviewed_by,
                   jobs.started_at, jobs.finished_at, jobs.updated_at,
                   jobs.template_key AS job_template_key,
                   jobs.template_revision AS job_template_revision,
                   messages.confirmation_template_key,
                   messages.confirmation_template_revision,
                   messages.payment_template_key,
                   messages.payment_template_revision,
                   followups.template_key AS followup_template_key,
                   followups.template_revision AS followup_template_revision
            FROM whatsapp_automation_jobs AS jobs
            LEFT JOIN whatsapp_messages AS messages
              ON jobs.job_kind = 'reservation_album'
             AND messages.message_id = jobs.message_id
            LEFT JOIN whatsapp_followup_messages AS followups
              ON jobs.job_kind = 'post_payment_followup'
             AND followups.message_id = jobs.message_id
            WHERE jobs.order_id = %s AND jobs.job_kind = %s
            ORDER BY jobs.created_at DESC
            LIMIT 1
            """,
            (order_id, job_kind),
        ).fetchone()
    if row is None:
        raise ValueError(f"WhatsApp automation job not found: {order_id}")
    payload = {
        key: (str(row[key]) if row[key] is not None else None)
        for key in (
            "job_key",
            "order_id",
            "job_kind",
            "status",
            "message_id",
            "error_message",
            "review_resolution",
            "review_note",
            "reviewed_at",
            "reviewed_by",
            "started_at",
            "finished_at",
            "updated_at",
        )
    }
    template_trace: list[dict[str, object]] = []
    for key_column, revision_column in (
        ("job_template_key", "job_template_revision"),
        ("confirmation_template_key", "confirmation_template_revision"),
        ("payment_template_key", "payment_template_revision"),
        ("followup_template_key", "followup_template_revision"),
    ):
        template_key = row[key_column]
        template_revision = row[revision_column]
        if template_key is None or template_revision is None:
            continue
        trace = {
            "template_key": str(template_key),
            "template_revision": int(template_revision),
        }
        if trace not in template_trace:
            template_trace.append(trace)
    payload["template_trace"] = template_trace
    return payload


def resolve_whatsapp_automation_review(
    job_key: str,
    *,
    resolution: str,
    note: str | None,
    reviewed_by: str,
    settings: Settings | None = None,
) -> dict[str, object]:
    normalized_resolution = resolution.strip().casefold()
    if normalized_resolution not in WHATSAPP_REVIEW_RESOLUTIONS:
        raise ValueError("Unsupported WhatsApp review resolution.")
    safe_note = sanitize_text(" ".join(str(note or "").split()))[:500] or None
    if normalized_resolution == "dismissed" and safe_note is None:
        raise ValueError("Indica el motivo para cerrar el pendiente sin envio.")
    actor = sanitize_text(" ".join(reviewed_by.split()))[:80] or "system"
    effective_settings = _settings(settings)
    init_database(effective_settings)
    now = _now()
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            """
            SELECT job_key, order_id, job_kind, status, message_id,
                   review_resolution, review_note, reviewed_at, reviewed_by
            FROM whatsapp_automation_jobs
            WHERE job_key = %s
            FOR UPDATE
            """,
            (job_key,),
        ).fetchone()
        if row is None:
            raise ValueError(f"WhatsApp automation job not found: {job_key}")
        if row["job_kind"] not in {"reservation_album", "post_payment_followup"}:
            raise ValueError("This WhatsApp job cannot be reconciled from the dashboard.")
        if row["status"] not in {"failed", "uncertain"}:
            raise ValueError("Only failed or uncertain WhatsApp jobs require reconciliation.")
        if row["review_resolution"] is not None:
            if str(row["review_resolution"]) != normalized_resolution:
                raise ValueError("This WhatsApp job already has a different resolution.")
            return {
                "job_key": str(row["job_key"]),
                "order_id": str(row["order_id"]),
                "status": str(row["status"]),
                "resolution": str(row["review_resolution"]),
                "note": row["review_note"],
                "reviewed_at": str(row["reviewed_at"]),
                "reviewed_by": str(row["reviewed_by"]),
            }
        if normalized_resolution in {"confirmed_complete", "completed_missing"}:
            if row["message_id"] is None:
                raise ValueError("The WhatsApp job has no prepared message to confirm.")
            message_table = (
                "whatsapp_messages"
                if row["job_kind"] == "reservation_album"
                else "whatsapp_followup_messages"
            )
            updated = connection.execute(
                f"""
                UPDATE {message_table}
                SET status = 'sent', sent_at = COALESCE(sent_at, %s), updated_at = %s
                WHERE message_id = %s
                RETURNING message_id
                """,
                (now, now, row["message_id"]),
            ).fetchone()
            if updated is None:
                raise ValueError("The prepared WhatsApp message no longer exists.")
        reviewed = connection.execute(
            """
            UPDATE whatsapp_automation_jobs
            SET review_resolution = %s,
                review_note = %s,
                reviewed_at = %s,
                reviewed_by = %s,
                updated_at = %s
            WHERE job_key = %s
            RETURNING job_key, order_id, status, review_resolution,
                      review_note, reviewed_at, reviewed_by
            """,
            (normalized_resolution, safe_note, now, actor, now, job_key),
        ).fetchone()
    return {
        "job_key": str(reviewed["job_key"]),
        "order_id": str(reviewed["order_id"]),
        "status": str(reviewed["status"]),
        "resolution": str(reviewed["review_resolution"]),
        "note": reviewed["review_note"],
        "reviewed_at": str(reviewed["reviewed_at"]),
        "reviewed_by": str(reviewed["reviewed_by"]),
    }


def _job_from_row(row) -> WhatsAppAutomationJob:
    raw_paths = row["attachment_paths"]
    return {
        "job_key": str(row["job_key"]),
        "order_id": str(row["order_id"]) if row["order_id"] is not None else None,
        "reservation_id": (
            str(row["reservation_id"]) if row["reservation_id"] is not None else None
        ),
        "job_kind": str(row["job_kind"]),
        "report_date": (
            str(row["report_date"]) if row["report_date"] is not None else None
        ),
        "appointment_day": (
            str(row["appointment_day"]) if row["appointment_day"] is not None else None
        ),
        "recipient_phone": (
            str(row["recipient_phone"]) if row["recipient_phone"] is not None else None
        ),
        "recipient_username": (
            str(row["recipient_username"])
            if row["recipient_username"] is not None
            else None
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
        "template_key": (
            str(row["template_key"]) if row["template_key"] is not None else None
        ),
        "template_revision": (
            int(row["template_revision"])
            if row["template_revision"] is not None
            else None
        ),
    }


def _international_phone(value: str) -> str:
    normalized = normalize_contact_whatsapp(value)
    if normalized is None:
        raise ValueError("El numero de WhatsApp es obligatorio.")
    return normalized


__all__ = [
    "WhatsAppAutomationJob",
    "WhatsAppAutomationKind",
    "block_whatsapp_automation_preflight",
    "claim_whatsapp_automation_job",
    "enqueue_appointment_reminder_job",
    "enqueue_daily_slot_summary_job",
    "enqueue_registration_notice_job",
    "enqueue_whatsapp_automation_job",
    "finish_whatsapp_automation_job",
    "get_order_whatsapp_review",
    "next_waiting_whatsapp_automation_job",
    "order_has_sent_whatsapp_message",
    "recover_expired_whatsapp_automation_jobs",
    "refresh_running_appointment_reminder_snapshot",
    "return_running_whatsapp_job_to_blocked",
    "resolve_whatsapp_automation_review",
    "whatsapp_automation_in_progress",
]
