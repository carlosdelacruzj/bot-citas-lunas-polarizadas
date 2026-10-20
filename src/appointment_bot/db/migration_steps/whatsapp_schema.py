from __future__ import annotations

from psycopg import Connection


def _create_whatsapp_messages_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_messages (
            message_id text PRIMARY KEY,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            message_kind text NOT NULL CHECK (
                message_kind IN ('test', 'reservation_confirmation_payment')
            ),
            recipient_phone text,
            recipient_username text,
            greeting text NOT NULL,
            evidence_caption text NOT NULL,
            payment_message text NOT NULL,
            attachment_path text NOT NULL,
            payment_attachment_path text,
            status text NOT NULL DEFAULT 'prepared' CHECK (status IN ('prepared', 'sent')),
            test_mode boolean NOT NULL DEFAULT false,
            prepared_at timestamptz NOT NULL,
            sent_at timestamptz,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_whatsapp_messages_sent CHECK (
                (status = 'prepared' AND sent_at IS NULL)
                OR (status = 'sent' AND sent_at IS NOT NULL)
            ),
            CONSTRAINT ck_whatsapp_messages_recipient CHECK (
                (recipient_phone IS NOT NULL)::integer
                + (recipient_username IS NOT NULL)::integer = 1
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_order_prepared
        ON whatsapp_messages(order_id, prepared_at DESC)
        """
    )


def _create_whatsapp_followup_messages_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_followup_messages (
            message_id text PRIMARY KEY,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            recipient_phone text,
            recipient_username text,
            steps jsonb NOT NULL,
            status text NOT NULL DEFAULT 'prepared' CHECK (status IN ('prepared', 'sent')),
            test_mode boolean NOT NULL DEFAULT false,
            prepared_at timestamptz NOT NULL,
            sent_at timestamptz,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_whatsapp_followup_messages_sent CHECK (
                (status = 'prepared' AND sent_at IS NULL)
                OR (status = 'sent' AND sent_at IS NOT NULL)
            ),
            CONSTRAINT ck_whatsapp_followup_messages_recipient CHECK (
                (recipient_phone IS NOT NULL)::integer
                + (recipient_username IS NOT NULL)::integer = 1
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_whatsapp_followup_messages_order_prepared
        ON whatsapp_followup_messages(order_id, prepared_at DESC)
        """
    )


def _create_whatsapp_automation_jobs_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_automation_jobs (
            job_key text PRIMARY KEY,
            order_id text REFERENCES service_orders(order_id) ON DELETE CASCADE,
            job_kind text NOT NULL,
            report_date date,
            recipient_phone text,
            recipient_username text,
            message_text text,
            publication_text text,
            attachment_paths jsonb,
            registration_notice_type text,
            preflight_cycle integer,
            status text NOT NULL DEFAULT 'queued',
            message_id text,
            attempt_count smallint NOT NULL DEFAULT 0 CHECK (
                attempt_count BETWEEN 0 AND 1
            ),
            lease_owner text,
            lease_expires_at timestamptz,
            error_message text,
            review_resolution text CHECK (
                review_resolution IS NULL OR review_resolution IN (
                    'confirmed_complete',
                    'completed_missing',
                    'dismissed'
                )
            ),
            review_note text,
            reviewed_at timestamptz,
            reviewed_by text,
            next_attempt_at timestamptz NOT NULL,
            preflight_error text,
            preflight_alerted_at timestamptz,
            created_at timestamptz NOT NULL,
            started_at timestamptz,
            finished_at timestamptz,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_whatsapp_automation_job_kind CHECK (
                job_kind IN (
                    'reservation_album',
                    'post_payment_followup',
                    'daily_slot_summary',
                    'registration_notice'
                )
            ),
            CONSTRAINT ck_whatsapp_automation_job_target CHECK (
                (
                    job_kind IN ('reservation_album', 'post_payment_followup')
                    AND order_id IS NOT NULL
                    AND report_date IS NULL
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
                    AND report_date IS NOT NULL
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
                    AND report_date IS NULL
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
            ),
            CONSTRAINT ck_whatsapp_automation_job_status CHECK (
                status IN ('queued', 'blocked', 'running', 'sent', 'failed', 'uncertain')
            ),
            CONSTRAINT ck_whatsapp_automation_job_attempt CHECK (
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
                    status IN ('sent', 'failed', 'uncertain')
                    AND attempt_count = 1
                    AND started_at IS NOT NULL
                    AND lease_owner IS NULL
                    AND lease_expires_at IS NULL
                    AND finished_at IS NOT NULL
                )
            ),
            CONSTRAINT ck_whatsapp_automation_job_review CHECK (
                (
                    review_resolution IS NULL
                    AND review_note IS NULL
                    AND reviewed_at IS NULL
                    AND reviewed_by IS NULL
                )
                OR (
                    review_resolution IS NOT NULL
                    AND reviewed_at IS NOT NULL
                    AND reviewed_by IS NOT NULL
                )
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_whatsapp_automation_jobs_queued
        ON whatsapp_automation_jobs(next_attempt_at, created_at)
        WHERE status IN ('queued', 'blocked')
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_whatsapp_automation_jobs_running
        ON whatsapp_automation_jobs((true))
        WHERE status = 'running'
        """
    )
