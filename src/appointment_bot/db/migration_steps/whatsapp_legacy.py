from __future__ import annotations

from psycopg import Connection


# Frozen creation schema from bdc75f9; later migrations add subsequent columns.
def create_legacy_whatsapp_messages_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_messages (
            message_id text PRIMARY KEY,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            message_kind text NOT NULL CHECK (
                message_kind IN ('test', 'reservation_confirmation_payment')
            ),
            recipient_phone text NOT NULL,
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


# Frozen creation schema from e9b4652; later migrations add subsequent columns.
def create_legacy_whatsapp_followup_messages_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_followup_messages (
            message_id text PRIMARY KEY,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            recipient_phone text NOT NULL,
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


# Frozen creation schema from ab902c4; later migrations add subsequent columns.
def create_legacy_whatsapp_automation_jobs_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_automation_jobs (
            job_key text PRIMARY KEY,
            order_id text NOT NULL REFERENCES service_orders(order_id) ON DELETE CASCADE,
            job_kind text NOT NULL CHECK (
                job_kind IN ('reservation_album', 'post_payment_followup')
            ),
            status text NOT NULL DEFAULT 'queued' CHECK (
                status IN ('queued', 'running', 'sent', 'failed', 'uncertain')
            ),
            message_id text,
            attempt_count smallint NOT NULL DEFAULT 0 CHECK (
                attempt_count BETWEEN 0 AND 1
            ),
            lease_owner text,
            lease_expires_at timestamptz,
            error_message text,
            created_at timestamptz NOT NULL,
            started_at timestamptz,
            finished_at timestamptz,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_whatsapp_automation_job_attempt CHECK (
                (status = 'queued' AND attempt_count = 0 AND started_at IS NULL)
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
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_whatsapp_automation_jobs_queued
        ON whatsapp_automation_jobs(created_at)
        WHERE status = 'queued'
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_whatsapp_automation_jobs_running
        ON whatsapp_automation_jobs((true))
        WHERE status = 'running'
        """
    )
