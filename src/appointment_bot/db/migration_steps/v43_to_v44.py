from __future__ import annotations

from psycopg import Connection


def v43_to_v44(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE order_state
            ADD COLUMN preflight_cycle integer NOT NULL DEFAULT 0
                CHECK (preflight_cycle >= 0)
            """
    )
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ADD COLUMN registration_notice_type text,
            ADD COLUMN preflight_cycle integer,
            DROP CONSTRAINT IF EXISTS whatsapp_automation_jobs_job_kind_check,
            DROP CONSTRAINT IF EXISTS ck_whatsapp_automation_job_kind,
            DROP CONSTRAINT IF EXISTS ck_whatsapp_automation_job_target
            """
    )
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ADD CONSTRAINT ck_whatsapp_automation_job_kind CHECK (
                job_kind IN (
                    'reservation_album',
                    'post_payment_followup',
                    'daily_slot_summary',
                    'registration_notice'
                )
            ),
            ADD CONSTRAINT ck_whatsapp_automation_job_target CHECK (
                (
                    job_kind IN ('reservation_album', 'post_payment_followup')
                    AND order_id IS NOT NULL
                    AND report_date IS NULL
                    AND recipient_phone IS NULL
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
                    AND message_text IS NOT NULL
                    AND jsonb_typeof(attachment_paths) = 'array'
                    AND registration_notice_type IS NULL
                    AND preflight_cycle IS NULL
                )
                OR (
                    job_kind = 'registration_notice'
                    AND order_id IS NOT NULL
                    AND report_date IS NULL
                    AND recipient_phone IS NOT NULL
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
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (44,),
    )
