from __future__ import annotations

from psycopg import Connection


def v44_to_v45(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE whatsapp_contacts
            ADD COLUMN username text
            """
    )
    connection.execute(
        """
            CREATE UNIQUE INDEX uq_whatsapp_contacts_username_lower
            ON whatsapp_contacts(lower(username))
            WHERE username IS NOT NULL
            """
    )
    connection.execute(
        """
            ALTER TABLE whatsapp_messages
            ADD COLUMN recipient_username text,
            ALTER COLUMN recipient_phone DROP NOT NULL,
            ADD CONSTRAINT ck_whatsapp_messages_recipient CHECK (
                (recipient_phone IS NOT NULL)::integer
                + (recipient_username IS NOT NULL)::integer = 1
            )
            """
    )
    connection.execute(
        """
            ALTER TABLE whatsapp_followup_messages
            ADD COLUMN recipient_username text,
            ALTER COLUMN recipient_phone DROP NOT NULL,
            ADD CONSTRAINT ck_whatsapp_followup_messages_recipient CHECK (
                (recipient_phone IS NOT NULL)::integer
                + (recipient_username IS NOT NULL)::integer = 1
            )
            """
    )
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ADD COLUMN recipient_username text,
            DROP CONSTRAINT ck_whatsapp_automation_job_target
            """
    )
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ADD CONSTRAINT ck_whatsapp_automation_job_target CHECK (
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
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (45,),
    )
