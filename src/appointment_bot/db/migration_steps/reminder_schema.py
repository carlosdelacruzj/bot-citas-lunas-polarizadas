from __future__ import annotations

from datetime import UTC, datetime

from psycopg import Connection


def _create_appointment_reminder_schema(connection: Connection) -> None:
    connection.execute(
        """
        ALTER TABLE reservations
        ADD COLUMN IF NOT EXISTS appointment_day date
        """
    )
    rows = connection.execute(
        """
        SELECT reservation_id, appointment_date
        FROM reservations
        WHERE appointment_day IS NULL AND appointment_date IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        appointment_day = _stored_appointment_day(row["appointment_date"])
        if appointment_day is None:
            continue
        connection.execute(
            "UPDATE reservations SET appointment_day = %s WHERE reservation_id = %s",
            (appointment_day, row["reservation_id"]),
        )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reservations_appointment_day_confirmed
        ON reservations(appointment_day, reserved_at DESC)
        WHERE status = 'confirmed'
        """
    )
    connection.execute(
        """
        ALTER TABLE whatsapp_automation_jobs
        ADD COLUMN IF NOT EXISTS reservation_id text,
        ADD COLUMN IF NOT EXISTS appointment_day date,
        ADD COLUMN IF NOT EXISTS priority smallint NOT NULL DEFAULT 50,
        DROP CONSTRAINT IF EXISTS whatsapp_automation_jobs_job_kind_check,
        DROP CONSTRAINT IF EXISTS ck_whatsapp_automation_job_kind,
        DROP CONSTRAINT IF EXISTS ck_whatsapp_automation_job_target,
        DROP CONSTRAINT IF EXISTS ck_whatsapp_automation_job_status,
        DROP CONSTRAINT IF EXISTS ck_whatsapp_automation_job_attempt,
        DROP CONSTRAINT IF EXISTS fk_whatsapp_automation_jobs_reservation
        """
    )
    connection.execute(
        """
        ALTER TABLE whatsapp_automation_jobs
        ADD CONSTRAINT fk_whatsapp_automation_jobs_reservation
            FOREIGN KEY (reservation_id, order_id)
            REFERENCES reservations(reservation_id, order_id) ON DELETE CASCADE,
        ADD CONSTRAINT ck_whatsapp_automation_job_kind CHECK (
            job_kind IN (
                'reservation_album',
                'post_payment_followup',
                'daily_slot_summary',
                'registration_notice',
                'appointment_reminder'
            )
        ),
        ADD CONSTRAINT ck_whatsapp_automation_job_target CHECK (
            (
                job_kind IN ('reservation_album', 'post_payment_followup')
                AND order_id IS NOT NULL
                AND reservation_id IS NULL
                AND report_date IS NULL
                AND appointment_day IS NULL
                AND recipient_phone IS NULL
                AND recipient_username IS NULL
                AND message_text IS NULL
                AND publication_text IS NULL
                AND attachment_paths IS NULL
                AND registration_notice_type IS NULL
                AND preflight_cycle IS NULL
            )
            OR (
                job_kind = 'daily_slot_summary'
                AND order_id IS NULL
                AND reservation_id IS NULL
                AND report_date IS NOT NULL
                AND appointment_day IS NULL
                AND recipient_phone IS NOT NULL
                AND recipient_username IS NULL
                AND message_text IS NOT NULL
                AND jsonb_typeof(attachment_paths) = 'array'
                AND registration_notice_type IS NULL
                AND preflight_cycle IS NULL
            )
            OR (
                job_kind = 'registration_notice'
                AND order_id IS NOT NULL
                AND reservation_id IS NULL
                AND report_date IS NULL
                AND appointment_day IS NULL
                AND (
                    (recipient_phone IS NOT NULL AND recipient_username IS NULL)
                    OR (recipient_phone IS NULL AND recipient_username IS NOT NULL)
                )
                AND message_text IS NOT NULL
                AND publication_text IS NULL
                AND attachment_paths IS NULL
                AND registration_notice_type IN (
                    'monitoring_started',
                    'no_pending_request',
                    'invalid_credentials'
                )
                AND preflight_cycle IS NOT NULL
                AND preflight_cycle > 0
            )
            OR (
                job_kind = 'appointment_reminder'
                AND order_id IS NOT NULL
                AND reservation_id IS NOT NULL
                AND report_date IS NOT NULL
                AND appointment_day IS NOT NULL
                AND (
                    (recipient_phone IS NOT NULL AND recipient_username IS NULL)
                    OR (recipient_phone IS NULL AND recipient_username IS NOT NULL)
                )
                AND message_text IS NOT NULL
                AND publication_text IS NULL
                AND attachment_paths IS NULL
                AND registration_notice_type IS NULL
                AND preflight_cycle IS NULL
            )
        ),
        ADD CONSTRAINT ck_whatsapp_automation_job_status CHECK (
            status IN ('queued', 'blocked', 'running', 'sent', 'failed', 'uncertain', 'skipped')
        ),
        ADD CONSTRAINT ck_whatsapp_automation_job_attempt CHECK (
            (
                status IN ('queued', 'blocked')
                AND attempt_count = 0
                AND started_at IS NULL
                AND lease_owner IS NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NULL
            )
            OR (
                status = 'running'
                AND attempt_count = 1
                AND started_at IS NOT NULL
                AND lease_owner IS NOT NULL
                AND lease_expires_at IS NOT NULL
                AND finished_at IS NULL
            )
            OR (
                status IN ('sent', 'failed', 'uncertain', 'skipped')
                AND attempt_count = 1
                AND started_at IS NOT NULL
                AND lease_owner IS NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NOT NULL
            )
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS appointment_reminder_days (
            service_date date PRIMARY KEY,
            appointment_day date NOT NULL,
            status text NOT NULL CHECK (
                status IN (
                    'disabled', 'dry_run', 'waiting_summary', 'ready',
                    'processing', 'complete', 'blocked', 'error'
                )
            ),
            summary_status text,
            eligible_count integer NOT NULL DEFAULT 0 CHECK (eligible_count >= 0),
            queued_count integer NOT NULL DEFAULT 0 CHECK (queued_count >= 0),
            existing_count integer NOT NULL DEFAULT 0 CHECK (existing_count >= 0),
            missing_contact_count integer NOT NULL DEFAULT 0 CHECK (
                missing_contact_count >= 0
            ),
            invalid_date_count integer NOT NULL DEFAULT 0 CHECK (invalid_date_count >= 0),
            last_error text,
            summary_alerted_at timestamptz,
            last_reconciled_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_appointment_reminder_day_target CHECK (
                appointment_day BETWEEN service_date + 1 AND service_date + 3
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_whatsapp_automation_jobs_priority
        ON whatsapp_automation_jobs(priority, next_attempt_at, created_at)
        WHERE status IN ('queued', 'blocked')
        """
    )


def _create_appointment_reminder_control_schema(connection: Connection) -> None:
    default_template = (
        "Hola, {nombre}. Te recordamos que el {fecha} tienes tu cita de "
        "lunas polarizadas. Hora: {hora}. Sede: {sede}. Si tu cita fue "
        "modificada recientemente, por favor comunícate con nosotros."
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS appointment_reminder_control (
            id integer PRIMARY KEY CHECK (id = 1),
            mode text NOT NULL DEFAULT 'disabled'
                CONSTRAINT ck_appointment_reminder_control_mode CHECK (
                    mode IN ('disabled', 'dry_run', 'live')
                ),
            lead_days smallint NOT NULL DEFAULT 1,
            message_template text NOT NULL CHECK (
                char_length(message_template) BETWEEN 1 AND 1000
            ),
            revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
            updated_at timestamptz NOT NULL,
            updated_by text NOT NULL,
            CONSTRAINT ck_appointment_reminder_control_lead_days CHECK (
                lead_days BETWEEN 1 AND 3
            )
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS appointment_reminder_template_versions (
            revision integer PRIMARY KEY CHECK (revision >= 1),
            message_template text NOT NULL CHECK (
                char_length(message_template) BETWEEN 1 AND 1000
            ),
            created_at timestamptz NOT NULL,
            created_by text NOT NULL
        )
        """
    )
    now = datetime.now(UTC)
    connection.execute(
        """
        INSERT INTO appointment_reminder_control (
            id, mode, message_template, revision, updated_at, updated_by
        ) VALUES (1, 'disabled', %s, 1, %s, 'schema-migration')
        ON CONFLICT (id) DO NOTHING
        """,
        (default_template, now),
    )
    connection.execute(
        """
        INSERT INTO appointment_reminder_template_versions (
            revision, message_template, created_at, created_by
        ) VALUES (1, %s, %s, 'schema-migration')
        ON CONFLICT (revision) DO NOTHING
        """,
        (default_template, now),
    )


def _create_current_appointment_reminder_control_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS appointment_reminder_control (
            id integer PRIMARY KEY CHECK (id = 1),
            mode text NOT NULL DEFAULT 'disabled'
                CONSTRAINT ck_appointment_reminder_control_mode CHECK (
                    mode IN ('disabled', 'dry_run', 'live')
                ),
            lead_days smallint NOT NULL DEFAULT 1,
            revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
            updated_at timestamptz NOT NULL,
            updated_by text NOT NULL,
            CONSTRAINT ck_appointment_reminder_control_lead_days CHECK (
                lead_days BETWEEN 1 AND 3
            )
        )
        """
    )
    connection.execute(
        """
        INSERT INTO appointment_reminder_control (
            id, mode, lead_days, revision, updated_at, updated_by
        ) VALUES (1, 'disabled', 1, 1, %s, 'schema-migration')
        ON CONFLICT (id) DO NOTHING
        """,
        (datetime.now(UTC),),
    )


def _create_appointment_reminder_lead_days_schema(connection: Connection) -> None:
    connection.execute(
        """
        ALTER TABLE appointment_reminder_control
        ADD COLUMN IF NOT EXISTS lead_days smallint NOT NULL DEFAULT 1
            CONSTRAINT ck_appointment_reminder_control_lead_days CHECK (
            lead_days BETWEEN 1 AND 3
        )
        """
    )
    connection.execute(
        """
        ALTER TABLE appointment_reminder_days
        DROP CONSTRAINT IF EXISTS ck_appointment_reminder_day_target,
        ADD CONSTRAINT ck_appointment_reminder_day_target CHECK (
            appointment_day BETWEEN service_date + 1 AND service_date + 3
        )
        """
    )


def _stored_appointment_day(value: object) -> object | None:
    text = str(value or "").strip()
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return None
