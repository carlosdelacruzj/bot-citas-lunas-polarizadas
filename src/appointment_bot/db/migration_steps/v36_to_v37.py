from __future__ import annotations

from psycopg import Connection


def v36_to_v37(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ADD COLUMN next_attempt_at timestamptz,
            ADD COLUMN preflight_error text,
            ADD COLUMN preflight_alerted_at timestamptz
            """
    )
    connection.execute(
        """
            UPDATE whatsapp_automation_jobs
            SET next_attempt_at = COALESCE(next_attempt_at, created_at)
            """
    )
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ALTER COLUMN next_attempt_at SET NOT NULL,
            DROP CONSTRAINT IF EXISTS whatsapp_automation_jobs_status_check,
            DROP CONSTRAINT IF EXISTS ck_whatsapp_automation_job_status,
            DROP CONSTRAINT ck_whatsapp_automation_job_attempt
            """
    )
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ADD CONSTRAINT ck_whatsapp_automation_job_status CHECK (
                status IN ('queued', 'blocked', 'running', 'sent', 'failed', 'uncertain')
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
                    status IN ('sent', 'failed', 'uncertain')
                    AND attempt_count = 1
                    AND started_at IS NOT NULL
                    AND lease_owner IS NULL
                    AND lease_expires_at IS NULL
                    AND finished_at IS NOT NULL
                )
            )
            """
    )
    connection.execute("DROP INDEX IF EXISTS idx_whatsapp_automation_jobs_queued")
    connection.execute(
        """
            CREATE INDEX idx_whatsapp_automation_jobs_queued
            ON whatsapp_automation_jobs(next_attempt_at, created_at)
            WHERE status IN ('queued', 'blocked')
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (37,),
    )
