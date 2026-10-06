from __future__ import annotations

from psycopg import Connection


def v39_to_v40(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ALTER COLUMN order_id DROP NOT NULL,
            ADD COLUMN report_date date,
            ADD COLUMN recipient_phone text,
            ADD COLUMN message_text text,
            ADD COLUMN attachment_paths jsonb,
            DROP CONSTRAINT IF EXISTS whatsapp_automation_jobs_job_kind_check
            """
    )
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ADD CONSTRAINT ck_whatsapp_automation_job_kind CHECK (
                job_kind IN (
                    'reservation_album',
                    'post_payment_followup',
                    'daily_slot_summary'
                )
            ),
            ADD CONSTRAINT ck_whatsapp_automation_job_target CHECK (
                (
                    job_kind IN ('reservation_album', 'post_payment_followup')
                    AND order_id IS NOT NULL
                    AND report_date IS NULL
                    AND recipient_phone IS NULL
                    AND message_text IS NULL
                    AND attachment_paths IS NULL
                )
                OR (
                    job_kind = 'daily_slot_summary'
                    AND order_id IS NULL
                    AND report_date IS NOT NULL
                    AND recipient_phone IS NOT NULL
                    AND message_text IS NOT NULL
                    AND jsonb_typeof(attachment_paths) = 'array'
                )
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (40,),
    )
