from __future__ import annotations

from datetime import date, timedelta
from typing import Any, TypedDict

from appointment_bot.config import Settings
from appointment_bot.core.rules import parse_appointment_date
from appointment_bot.db.common import _connection, _database_url, _now, init_database

EXCLUDED_CLOSURE_REASONS = (
    "client_withdrew",
    "external_slot",
    "duplicate",
    "not_serviceable",
    "uncollectible",
)


class AppointmentReminderCandidate(TypedDict):
    reservation_id: str
    order_id: str
    applicant_name: str | None
    contact_name: str | None
    recipient_phone: str | None
    recipient_username: str | None
    site: str | None
    appointment_date: str | None
    appointment_day: date
    appointment_hour: str | None


def backfill_missing_appointment_days(*, settings: Settings) -> tuple[int, int]:
    init_database(settings)
    updated = 0
    invalid = 0
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT reservation_id, appointment_date
            FROM reservations
            WHERE appointment_day IS NULL AND appointment_date IS NOT NULL
            """
        ).fetchall()
        for row in rows:
            appointment_day = parse_appointment_date(str(row["appointment_date"]))
            if appointment_day is None:
                invalid += 1
                continue
            connection.execute(
                """
                UPDATE reservations
                SET appointment_day = %s, updated_at = %s
                WHERE reservation_id = %s AND appointment_day IS NULL
                """,
                (appointment_day, _now(), row["reservation_id"]),
            )
            updated += 1
    return updated, invalid


def list_appointment_reminder_candidates(
    appointment_day: date,
    *,
    settings: Settings,
) -> list[AppointmentReminderCandidate]:
    init_database(settings)
    closure_placeholders = ", ".join(["%s"] * len(EXCLUDED_CLOSURE_REASONS))
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            f"""
            WITH latest_confirmed AS (
                SELECT DISTINCT ON (r.order_id)
                       r.reservation_id, r.order_id, r.site, r.appointment_date,
                       r.appointment_day, r.appointment_hour, r.reserved_at, r.created_at
                FROM reservations r
                WHERE r.status = 'confirmed'
                ORDER BY r.order_id, r.reserved_at DESC, r.created_at DESC
            )
            SELECT latest.reservation_id, latest.order_id, a.full_name AS applicant_name,
                   contact.display_name AS contact_name, contact.phone AS recipient_phone,
                   contact.username AS recipient_username, latest.site,
                   latest.appointment_date, latest.appointment_day, latest.appointment_hour
            FROM latest_confirmed latest
            JOIN service_orders so ON so.order_id = latest.order_id
            JOIN applicants a ON a.applicant_id = so.applicant_id
            LEFT JOIN LATERAL (
                SELECT wc.phone, wc.username, wc.display_name
                FROM applicant_contacts ac
                JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
                WHERE ac.applicant_id = so.applicant_id AND ac.is_primary = true
                ORDER BY ac.updated_at DESC
                LIMIT 1
            ) contact ON true
            WHERE latest.appointment_day = %s
              AND so.status IN ('reserved_payment_pending', 'paid', 'archived')
              AND (
                    so.closure_reason IS NULL
                    OR so.closure_reason NOT IN ({closure_placeholders})
              )
            ORDER BY latest.appointment_hour NULLS LAST, latest.reserved_at, latest.order_id
            """,
            (appointment_day, *EXCLUDED_CLOSURE_REASONS),
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


def get_current_appointment_reminder_candidate(
    reservation_id: str,
    appointment_day: date,
    *,
    settings: Settings,
) -> AppointmentReminderCandidate | None:
    init_database(settings)
    closure_placeholders = ", ".join(["%s"] * len(EXCLUDED_CLOSURE_REASONS))
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            f"""
            SELECT r.reservation_id, r.order_id, a.full_name AS applicant_name,
                   contact.display_name AS contact_name, contact.phone AS recipient_phone,
                   contact.username AS recipient_username, r.site, r.appointment_date,
                   r.appointment_day, r.appointment_hour
            FROM reservations r
            JOIN service_orders so ON so.order_id = r.order_id
            JOIN applicants a ON a.applicant_id = so.applicant_id
            LEFT JOIN LATERAL (
                SELECT wc.phone, wc.username, wc.display_name
                FROM applicant_contacts ac
                JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
                WHERE ac.applicant_id = so.applicant_id AND ac.is_primary = true
                ORDER BY ac.updated_at DESC
                LIMIT 1
            ) contact ON true
            WHERE r.reservation_id = %s
              AND r.status = 'confirmed'
              AND r.appointment_day = %s
              AND so.status IN ('reserved_payment_pending', 'paid', 'archived')
              AND (
                    so.closure_reason IS NULL
                    OR so.closure_reason NOT IN ({closure_placeholders})
              )
              AND NOT EXISTS (
                    SELECT 1
                    FROM reservations newer
                    WHERE newer.order_id = r.order_id
                      AND newer.status = 'confirmed'
                      AND (newer.reserved_at, newer.created_at) > (r.reserved_at, r.created_at)
              )
            """,
            (reservation_id, appointment_day, *EXCLUDED_CLOSURE_REASONS),
        ).fetchone()
    return _candidate_from_row(row) if row is not None else None


def count_invalid_current_appointment_dates(*, settings: Settings) -> int:
    init_database(settings)
    closure_placeholders = ", ".join(["%s"] * len(EXCLUDED_CLOSURE_REASONS))
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            f"""
            WITH latest_confirmed AS (
                SELECT DISTINCT ON (r.order_id)
                       r.order_id, r.appointment_date, r.appointment_day
                FROM reservations r
                WHERE r.status = 'confirmed'
                ORDER BY r.order_id, r.reserved_at DESC, r.created_at DESC
            )
            SELECT COUNT(*) AS total
            FROM latest_confirmed latest
            JOIN service_orders so ON so.order_id = latest.order_id
            WHERE latest.appointment_day IS NULL
              AND so.status IN ('reserved_payment_pending', 'paid', 'archived')
              AND (
                    so.closure_reason IS NULL
                    OR so.closure_reason NOT IN ({closure_placeholders})
              )
            """,
            EXCLUDED_CLOSURE_REASONS,
        ).fetchone()
    return int(row["total"] if row is not None else 0)


def daily_summary_barrier_status(
    service_date: date,
    *,
    settings: Settings,
) -> str:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT status
            FROM whatsapp_automation_jobs
            WHERE job_kind = 'daily_slot_summary' AND report_date = %s
            ORDER BY created_at DESC
            """,
            (service_date,),
        ).fetchall()
    statuses = [str(row["status"]) for row in rows]
    if not statuses:
        return "missing"
    if any(status in {"queued", "blocked", "running"} for status in statuses):
        return "active"
    return statuses[0]


def appointment_reminder_job_counts(
    service_date: date,
    appointment_day: date,
    *,
    settings: Settings,
) -> dict[str, int]:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM whatsapp_automation_jobs
            WHERE job_kind = 'appointment_reminder'
              AND report_date = %s
              AND appointment_day = %s
            GROUP BY status
            """,
            (service_date, appointment_day),
        ).fetchall()
    return {str(row["status"]): int(row["total"]) for row in rows}


def ensure_appointment_reminder_batch_day(
    service_date: date,
    configured_lead_days: int,
    *,
    settings: Settings,
) -> date:
    init_database(settings)
    appointment_day = service_date + timedelta(days=configured_lead_days)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            INSERT INTO appointment_reminder_days (
                service_date, appointment_day, status, summary_status,
                last_reconciled_at, created_at, updated_at
            )
            VALUES (%s, %s, 'disabled', NULL, %s, %s, %s)
            ON CONFLICT(service_date) DO UPDATE SET
                service_date = appointment_reminder_days.service_date
            RETURNING appointment_day
            """,
            (service_date, appointment_day, now, now, now),
        ).fetchone()
    if row is None:
        raise RuntimeError("Appointment reminder batch day could not be frozen.")
    return row["appointment_day"]


def record_appointment_reminder_day(
    *,
    service_date: date,
    appointment_day: date,
    status: str,
    summary_status: str,
    eligible_count: int,
    queued_count: int,
    existing_count: int,
    missing_contact_count: int,
    invalid_date_count: int,
    last_error: str | None,
    settings: Settings,
) -> None:
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO appointment_reminder_days (
                service_date, appointment_day, status, summary_status,
                eligible_count, queued_count, existing_count, missing_contact_count,
                invalid_date_count, last_error, last_reconciled_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(service_date) DO UPDATE SET
                appointment_day = excluded.appointment_day,
                status = excluded.status,
                summary_status = excluded.summary_status,
                eligible_count = excluded.eligible_count,
                queued_count = CASE
                    WHEN appointment_reminder_days.appointment_day = excluded.appointment_day
                    THEN appointment_reminder_days.queued_count + excluded.queued_count
                    ELSE excluded.queued_count
                END,
                existing_count = excluded.existing_count,
                missing_contact_count = excluded.missing_contact_count,
                invalid_date_count = excluded.invalid_date_count,
                last_error = excluded.last_error,
                summary_alerted_at = CASE
                    WHEN appointment_reminder_days.appointment_day = excluded.appointment_day
                    THEN appointment_reminder_days.summary_alerted_at
                    ELSE NULL
                END,
                last_reconciled_at = excluded.last_reconciled_at,
                updated_at = excluded.updated_at
            """,
            (
                service_date,
                appointment_day,
                status,
                summary_status,
                eligible_count,
                queued_count,
                existing_count,
                missing_contact_count,
                invalid_date_count,
                last_error,
                now,
                now,
                now,
            ),
        )


def mark_daily_summary_missing_alerted(
    service_date: date,
    *,
    settings: Settings,
) -> bool:
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE appointment_reminder_days
            SET summary_alerted_at = %s, updated_at = %s
            WHERE service_date = %s AND summary_alerted_at IS NULL
            RETURNING service_date
            """,
            (now, now, service_date),
        ).fetchone()
    return row is not None


def appointment_reminder_status(
    service_date: date,
    lead_days: int,
    *,
    settings: Settings,
) -> dict[str, Any]:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        day = connection.execute(
            """
            SELECT service_date, appointment_day, status, summary_status,
                   eligible_count, queued_count, existing_count, missing_contact_count,
                   invalid_date_count, last_error, summary_alerted_at,
                   last_reconciled_at, created_at, updated_at
            FROM appointment_reminder_days
            WHERE service_date = %s
            """,
            (service_date,),
        ).fetchone()
        appointment_day = (
            day["appointment_day"]
            if day is not None
            else service_date + timedelta(days=lead_days)
        )
        count_rows = connection.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM whatsapp_automation_jobs
            WHERE job_kind = 'appointment_reminder'
              AND report_date = %s
              AND appointment_day = %s
            GROUP BY status
            """,
            (service_date, appointment_day),
        ).fetchall()
        jobs = connection.execute(
            """
            SELECT job_key, order_id, appointment_day, recipient_phone,
                   recipient_username, status, error_message, created_at,
                   started_at, finished_at, updated_at
            FROM whatsapp_automation_jobs
            WHERE job_kind = 'appointment_reminder'
              AND appointment_day = %s
            ORDER BY report_date DESC, created_at, job_key
            LIMIT 200
            """,
            (appointment_day,),
        ).fetchall()
    counts = {str(row["status"]): int(row["total"]) for row in count_rows}
    return {
        "service_date": service_date.isoformat(),
        "appointment_day": appointment_day.isoformat(),
        "day": _day_payload(day),
        "job_counts": counts,
        "jobs": [
            {
                "job_key": str(row["job_key"]),
                "order_id": str(row["order_id"]),
                "appointment_day": str(row["appointment_day"]),
                "recipient": _masked_recipient(row["recipient_phone"], row["recipient_username"]),
                "status": str(row["status"]),
                "error_message": row["error_message"],
                "created_at": _iso(row["created_at"]),
                "started_at": _iso(row["started_at"]),
                "finished_at": _iso(row["finished_at"]),
                "updated_at": _iso(row["updated_at"]),
            }
            for row in jobs
        ],
    }


def _candidate_from_row(row) -> AppointmentReminderCandidate:
    return {
        "reservation_id": str(row["reservation_id"]),
        "order_id": str(row["order_id"]),
        "applicant_name": row["applicant_name"],
        "contact_name": row["contact_name"],
        "recipient_phone": row["recipient_phone"],
        "recipient_username": row["recipient_username"],
        "site": row["site"],
        "appointment_date": row["appointment_date"],
        "appointment_day": row["appointment_day"],
        "appointment_hour": row["appointment_hour"],
    }


def _day_payload(row) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        key: _iso(value) if hasattr(value, "isoformat") else value
        for key, value in dict(row).items()
    }


def _masked_recipient(phone: object, username: object) -> str:
    if phone:
        digits = "".join(character for character in str(phone) if character.isdigit())
        return f"+***{digits[-4:]}" if digits else "telefono configurado"
    if username:
        text = str(username).lstrip("@")
        return f"@{text[:2]}***{text[-1:]}" if text else "usuario configurado"
    return "sin contacto"


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else str(value)


__all__ = [
    "AppointmentReminderCandidate",
    "appointment_reminder_job_counts",
    "appointment_reminder_status",
    "backfill_missing_appointment_days",
    "count_invalid_current_appointment_dates",
    "daily_summary_barrier_status",
    "ensure_appointment_reminder_batch_day",
    "get_current_appointment_reminder_candidate",
    "list_appointment_reminder_candidates",
    "mark_daily_summary_missing_alerted",
    "record_appointment_reminder_day",
]
