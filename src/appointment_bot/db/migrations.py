from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.captcha_schema import (
    _create_captcha_authority_schema,
    _create_captcha_sampling_control_schema,
    _create_captcha_shadow_outbox_schema,
)
from appointment_bot.db.migration_steps.finance_schema import (
    _create_finance_month_closure_schema,
    _create_finance_schema,
    _create_payment_receipt_triggers,
)
from appointment_bot.db.migration_steps.opportunity_schema import (
    _create_opportunity_observability_schema,
    _promote_stable_runtime_schema,
)
from appointment_bot.db.migration_steps.order_schema import (
    _create_observer_window_metrics_schema,
    _create_order_checks_schema,
)
from appointment_bot.db.migration_steps.post_appointment_schema import (
    _create_post_appointment_schema,
)
from appointment_bot.db.migration_steps.reminder_schema import (
    _create_appointment_reminder_control_schema,
    _create_appointment_reminder_lead_days_schema,
    _create_appointment_reminder_schema,
)
from appointment_bot.db.migration_steps.reservation_schema import (
    _create_reservation_attempts_schema,
    _create_reservation_program_identity_schema,
)
from appointment_bot.db.migration_steps.template_schema import (
    _create_whatsapp_automation_template_trace_schema,
    _create_whatsapp_followup_template_trace_schema,
    _create_whatsapp_message_template_schema,
    _create_whatsapp_message_template_trace_schema,
    _freeze_historical_whatsapp_followup_text,
    _retire_appointment_reminder_legacy_schema,
    _unify_appointment_reminder_template_schema,
)
from appointment_bot.db.migration_steps.whatsapp_legacy import (
    create_legacy_whatsapp_automation_jobs_schema,
    create_legacy_whatsapp_followup_messages_schema,
    create_legacy_whatsapp_messages_schema,
)
from appointment_bot.db.migration_steps.worker_schema import (
    _create_remote_control_audit_schema,
    _create_telegram_alert_outbox_schema,
    _create_worker_commands_schema,
)
from appointment_bot.db.schema_definition import create_current_schema
from appointment_bot.db.schema_validation import validate_current_schema

SCHEMA_VERSION = 74
_MIGRATION_LOCK_ID = 1_047_296_811


def migrate_database(connection: Connection) -> None:
    """Create the current schema or reject unsupported schema versions atomically."""
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_ID,))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id integer PRIMARY KEY CHECK (id = 1),
            version integer NOT NULL CHECK (version >= 0)
        )
        """
    )
    row = connection.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    if row is None:
        create_current_schema(connection)
        validate_current_schema(connection, SCHEMA_VERSION)
        connection.execute(
            "INSERT INTO schema_version (id, version) VALUES (1, %s)",
            (SCHEMA_VERSION,),
        )
        return

    current_version = int(row["version"])
    if current_version == 14:
        _create_order_checks_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (15,),
        )
        current_version = 15
    if current_version == 15:
        _create_reservation_attempts_schema(connection)
        connection.execute(
            """
            INSERT INTO reservation_attempts (
                attempt_id, order_id, idempotency_key, status, created_at, updated_at
            )
            SELECT 'legacy:' || order_id,
                   order_id,
                   'legacy:' || order_id,
                   CASE WHEN last_status = 'submission_intent' THEN 'intent' ELSE 'unknown' END,
                   COALESCE(last_run_at, CURRENT_TIMESTAMP),
                   CURRENT_TIMESTAMP
            FROM order_state
            WHERE last_status IN (
                'submission_intent', 'submission_pending', 'reservation_unconfirmed'
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (16,),
        )
        current_version = 16
    if current_version == 16:
        connection.execute(
            """
            ALTER TABLE order_state
            ADD COLUMN credential_failures integer NOT NULL DEFAULT 0
                CHECK (credential_failures >= 0)
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (17,),
        )
        current_version = 17
    if current_version == 17:
        _create_observer_window_metrics_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (18,),
        )
        current_version = 18
    if current_version == 18:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN minimum_date date
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (19,),
        )
        current_version = 19
    if current_version == 19:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN allowed_weekdays smallint[] CHECK (
                allowed_weekdays IS NULL
                OR allowed_weekdays <@ ARRAY[1,2,3,4,5,6,7]::smallint[]
            )
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (20,),
        )
        current_version = 20
    if current_version == 20:
        connection.execute(
            """
            ALTER TABLE order_state
            ADD COLUMN program_listing jsonb
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (21,),
        )
        current_version = 21
    if current_version == 21:
        connection.execute(
            """
            ALTER TABLE whatsapp_contacts
            ADD COLUMN contact_source text NOT NULL DEFAULT 'whatsapp'
            """
        )
        connection.execute("ALTER TABLE whatsapp_contacts ALTER COLUMN phone DROP NOT NULL")
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (22,),
        )
        current_version = 22
    if current_version == 22:
        _create_worker_commands_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (23,),
        )
        current_version = 23
    if current_version == 23:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN parent_order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN program_expediente text
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN program_plate text
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (24,),
        )
        current_version = 24
    if current_version == 24:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN closure_reason text CHECK (
                closure_reason IS NULL OR closure_reason IN (
                    'completed_by_us',
                    'family_no_charge',
                    'client_withdrew',
                    'external_slot',
                    'duplicate',
                    'not_serviceable'
                )
            )
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN closure_note text
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN closed_at timestamptz
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (25,),
        )
        current_version = 25
    if current_version == 25:
        _create_finance_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (26,),
        )
        current_version = 26
    if current_version == 26:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN maximum_date date
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD CONSTRAINT ck_service_orders_reservation_date_range CHECK (
                maximum_date IS NULL OR minimum_date IS NULL OR maximum_date >= minimum_date
            )
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (27,),
        )
        current_version = 27
    if current_version == 27:
        create_legacy_whatsapp_messages_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (28,),
        )
        current_version = 28
    if current_version == 28:
        connection.execute(
            """
            ALTER TABLE whatsapp_messages
            ADD COLUMN IF NOT EXISTS payment_attachment_path text
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (29,),
        )
        current_version = 29
    if current_version == 29:
        create_legacy_whatsapp_followup_messages_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (30,),
        )
        current_version = 30
    if current_version == 30:
        connection.execute(
            """
            ALTER TABLE portal_accounts
            ADD COLUMN document_type text NOT NULL DEFAULT 'dni' CHECK (
                document_type IN ('dni', 'foreign_resident_card')
            )
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (31,),
        )
        current_version = 31
    if current_version == 31:
        connection.execute(
            """
            ALTER TABLE order_state
            ADD COLUMN preflight_status text NOT NULL DEFAULT 'not_required' CHECK (
                preflight_status IN ('not_required', 'pending', 'running', 'validated', 'failed')
            ),
            ADD COLUMN preflight_message text,
            ADD COLUMN preflight_started_at timestamptz,
            ADD COLUMN preflight_validated_at timestamptz,
            ADD COLUMN preflight_details jsonb
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (32,),
        )
        current_version = 32
    if current_version == 32:
        _create_remote_control_audit_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (33,),
        )
        current_version = 33
    if current_version == 33:
        _create_captcha_shadow_outbox_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (34,),
        )
        current_version = 34
    if current_version == 34:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN excluded_date_ranges jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
                jsonb_typeof(excluded_date_ranges) = 'array'
            )
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (35,),
        )
        current_version = 35
    if current_version == 35:
        create_legacy_whatsapp_automation_jobs_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (36,),
        )
        current_version = 36
    if current_version == 36:
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
        current_version = 37
    if current_version == 37:
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (38,),
        )
        current_version = 38
    if current_version == 38:
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (39,),
        )
        current_version = 39
    if current_version == 39:
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
        current_version = 40
    if current_version == 40:
        connection.execute(
            """
            ALTER TABLE whatsapp_automation_jobs
            ADD COLUMN publication_text text,
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
                    AND message_text IS NULL
                    AND publication_text IS NULL
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
            (41,),
        )
        current_version = 41
    if current_version == 41:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN reservation_price numeric(12, 2) NOT NULL DEFAULT 40.00
                CHECK (reservation_price > 0)
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            ALTER COLUMN reservation_price SET DEFAULT 50.00
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (42,),
        )
        current_version = 42
    if current_version == 42:
        connection.execute("DROP TABLE IF EXISTS hosted_registration_contacts")
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (43,),
        )
        current_version = 43
    if current_version == 43:
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
        current_version = 44
    if current_version == 44:
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
        current_version = 45
    if current_version == 45:
        connection.execute(
            """
            ALTER TABLE service_orders
            DROP CONSTRAINT service_orders_closure_reason_check,
            ADD CONSTRAINT service_orders_closure_reason_check CHECK (
                closure_reason IS NULL OR closure_reason IN (
                    'completed_by_us',
                    'family_no_charge',
                    'client_withdrew',
                    'external_slot',
                    'duplicate',
                    'not_serviceable',
                    'uncollectible'
                )
            )
            """
        )
        connection.execute(
            """
            ALTER TABLE payments
            DROP CONSTRAINT payments_status_check,
            ADD CONSTRAINT payments_status_check CHECK (
                status IN ('pending', 'paid', 'written_off')
            )
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (46,),
        )
        current_version = 46
    if current_version == 46:
        _create_captcha_sampling_control_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (47,),
        )
        current_version = 47
    if current_version == 47:
        _create_post_appointment_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (48,),
        )
        current_version = 48
    if current_version == 48:
        _create_reservation_program_identity_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (49,),
        )
        current_version = 49
    if current_version == 49:
        _create_opportunity_observability_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (50,),
        )
        current_version = 50
    if current_version == 50:
        _create_captcha_authority_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (51,),
        )
        current_version = 51
    if current_version == 51:
        _create_finance_month_closure_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (52,),
        )
        current_version = 52
    if current_version == 52:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN acquisition_source text
            """
        )
        connection.execute(
            """
            UPDATE service_orders so
            SET acquisition_source = NULLIF(BTRIM(wc.contact_source), '')
            FROM applicant_contacts ac
            JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            WHERE ac.applicant_id = so.applicant_id
              AND ac.is_primary = true
              AND so.acquisition_source IS NULL
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (53,),
        )
        current_version = 53
    if current_version == 53:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN acquisition_source_origin text CHECK (
                acquisition_source_origin IS NULL OR acquisition_source_origin IN (
                    'order_creation', 'historical_backfill'
                )
            )
            """
        )
        connection.execute(
            """
            UPDATE service_orders
            SET acquisition_source_origin = 'historical_backfill'
            WHERE acquisition_source IS NOT NULL
              AND acquisition_source_origin IS NULL
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (54,),
        )
        current_version = 54
    if current_version == 54:
        _create_telegram_alert_outbox_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (55,),
        )
        current_version = 55
    if current_version == 55:
        _create_appointment_reminder_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (56,),
        )
        current_version = 56
    if current_version == 56:
        _create_appointment_reminder_control_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (57,),
        )
        current_version = 57
    if current_version == 57:
        connection.execute(
            """
            ALTER TABLE whatsapp_automation_jobs
            ADD COLUMN review_resolution text CHECK (
                review_resolution IS NULL OR review_resolution IN (
                    'confirmed_complete',
                    'completed_missing',
                    'dismissed'
                )
            ),
            ADD COLUMN review_note text,
            ADD COLUMN reviewed_at timestamptz,
            ADD COLUMN reviewed_by text,
            ADD CONSTRAINT ck_whatsapp_automation_job_review CHECK (
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
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (58,),
        )
        current_version = 58
    if current_version == 58:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN service_type text NOT NULL DEFAULT 'standard' CHECK (
                service_type IN ('standard', 'selected_date', 'custom')
            )
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (59,),
        )
        current_version = 59
    if current_version == 59:
        connection.execute(
            """
            ALTER TABLE service_orders
            DROP CONSTRAINT IF EXISTS service_orders_service_type_check
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            DROP CONSTRAINT IF EXISTS ck_service_orders_service_type
            """
        )
        connection.execute(
            """
            UPDATE service_orders
            SET service_type = 'selected_weekday',
                allowed_weekdays = ARRAY[
                    EXTRACT(ISODOW FROM minimum_date)::smallint
                ],
                minimum_date = NULL,
                maximum_date = NULL
            WHERE service_type = 'selected_date'
              AND minimum_date IS NOT NULL
              AND minimum_date = maximum_date
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD CONSTRAINT ck_service_orders_service_type CHECK (
                service_type IN ('standard', 'selected_weekday', 'custom')
            )
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (60,),
        )
        current_version = 60
    if current_version == 60:
        _create_whatsapp_message_template_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (61,),
        )
        current_version = 61
    if current_version == 61:
        _create_whatsapp_automation_template_trace_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (62,),
        )
        current_version = 62
    if current_version == 62:
        _create_whatsapp_message_template_trace_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (63,),
        )
        current_version = 63
    if current_version == 63:
        _create_whatsapp_followup_template_trace_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (64,),
        )
        current_version = 64
    if current_version == 64:
        _unify_appointment_reminder_template_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (65,),
        )
        current_version = 65
    if current_version == 65:
        _create_appointment_reminder_lead_days_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (66,),
        )
        current_version = 66
    if current_version == 66:
        _create_post_appointment_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (67,),
        )
        current_version = 67
    if current_version == 67:
        _promote_stable_runtime_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (68,),
        )
        current_version = 68
    if current_version == 68:
        _retire_appointment_reminder_legacy_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (69,),
        )
        current_version = 69
    if current_version == 69:
        _freeze_historical_whatsapp_followup_text(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (70,),
        )
        current_version = 70
    if current_version == 70:
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD COLUMN service_package text NOT NULL DEFAULT 'standard',
            ADD COLUMN official_fee_amount numeric(12, 2) NOT NULL DEFAULT 0,
            ADD COLUMN initial_payment_amount numeric(12, 2) NOT NULL DEFAULT 0
            """
        )
        connection.execute(
            """
            UPDATE service_orders
            SET service_package = CASE
                    WHEN service_type = 'selected_weekday' THEN 'restricted'
                    WHEN service_type = 'custom' THEN 'custom'
                    ELSE 'standard'
                END
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD CONSTRAINT ck_service_orders_service_package CHECK (
                service_package IN ('standard', 'restricted', 'integral', 'custom')
            ),
            ADD CONSTRAINT ck_service_orders_official_fee CHECK (
                official_fee_amount >= 0 AND official_fee_amount <= reservation_price
            ),
            ADD CONSTRAINT ck_service_orders_initial_payment CHECK (
                initial_payment_amount >= 0 AND initial_payment_amount <= reservation_price
            )
            """
        )
        connection.execute(
            """
            INSERT INTO finance_categories (
                category_code, display_name, cost_behavior, created_at, updated_at
            )
            VALUES (
                'government_fee', 'Tasas oficiales por cuenta del cliente',
                'variable', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (category_code) DO UPDATE SET
                display_name = excluded.display_name,
                cost_behavior = excluded.cost_behavior,
                active = true,
                updated_at = excluded.updated_at
            """
        )
        connection.execute(
            """
            CREATE TABLE payment_receipts (
                receipt_id text PRIMARY KEY,
                payment_id text NOT NULL REFERENCES payments(payment_id) ON DELETE CASCADE,
                order_id text NOT NULL REFERENCES service_orders(order_id) ON DELETE CASCADE,
                amount numeric(12, 2) NOT NULL CHECK (amount > 0),
                received_at timestamptz NOT NULL,
                source text NOT NULL,
                actor text,
                created_at timestamptz NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX idx_payment_receipts_received
            ON payment_receipts(received_at, order_id)
            """
        )
        connection.execute(
            """
            INSERT INTO payment_receipts (
                receipt_id, payment_id, order_id, amount, received_at, source, created_at
            )
            SELECT 'legacy:' || payment_id, payment_id, order_id, amount_paid,
                   COALESCE(paid_at, updated_at, created_at), 'historical_backfill',
                   CURRENT_TIMESTAMP
            FROM payments
            WHERE amount_paid > 0
            ON CONFLICT(receipt_id) DO NOTHING
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (71,),
        )
        current_version = 71
    if current_version == 71:
        connection.execute(
            """
            ALTER TABLE opportunity_bursts
            DROP CONSTRAINT IF EXISTS opportunity_bursts_configured_max_sessions_check,
            DROP CONSTRAINT IF EXISTS opportunity_bursts_max_active_sessions_check,
            DROP CONSTRAINT IF EXISTS ck_opportunity_bursts_configured_max_sessions,
            DROP CONSTRAINT IF EXISTS ck_opportunity_bursts_max_active_sessions
            """
        )
        connection.execute(
            """
            ALTER TABLE opportunity_bursts
            ADD CONSTRAINT ck_opportunity_bursts_configured_max_sessions CHECK (
                configured_max_sessions BETWEEN 1 AND 3
            ),
            ADD CONSTRAINT ck_opportunity_bursts_max_active_sessions CHECK (
                max_active_sessions BETWEEN 0 AND 3
            )
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (72,),
        )
        current_version = 72
    if current_version == 72:
        connection.execute(
            """
            UPDATE service_orders
            SET service_type = 'standard'
            WHERE service_package = 'integral'
              AND service_type <> 'standard'
              AND status = 'paid'
              AND charge_required = true
              AND reservation_price = 160.00
              AND official_fee_amount = 71.40
              AND initial_payment_amount = 80.00
            """
        )
        connection.execute(
            """
            ALTER TABLE service_orders
            ADD CONSTRAINT ck_service_orders_integral_terms CHECK (
                service_package <> 'integral' OR (
                    charge_required = true
                    AND service_type = 'standard'
                    AND reservation_price = 160.00
                    AND official_fee_amount = 71.40
                    AND initial_payment_amount = 80.00
                    AND (
                        status <> 'archived'
                        OR COALESCE(closure_reason = 'uncollectible', false)
                    )
                )
            )
            """
        )
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (73,),
        )
        current_version = 73
    if current_version == 73:
        inconsistent_receipts = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM payment_receipts receipt
            LEFT JOIN payments payment
              ON payment.payment_id = receipt.payment_id
             AND payment.order_id = receipt.order_id
            WHERE payment.payment_id IS NULL
            """
        ).fetchone()
        if inconsistent_receipts is None or int(inconsistent_receipts["count"] or 0):
            raise RuntimeError(
                "Database schema v74 migration found payment_receipts that do not "
                "belong to the referenced payment and order."
            )
        connection.execute(
            """
            ALTER TABLE payments
            ADD CONSTRAINT uq_payments_payment_order UNIQUE (payment_id, order_id)
            """
        )
        connection.execute(
            """
            ALTER TABLE payment_receipts
            ADD COLUMN corrects_receipt_id text,
            ADD COLUMN correction_reason text,
            DROP CONSTRAINT payment_receipts_payment_id_fkey,
            DROP CONSTRAINT payment_receipts_order_id_fkey,
            DROP CONSTRAINT payment_receipts_amount_check,
            ADD CONSTRAINT uq_payment_receipts_identity_payment_order
                UNIQUE (receipt_id, payment_id, order_id),
            ADD CONSTRAINT fk_payment_receipts_payment_order
                FOREIGN KEY (payment_id, order_id)
                REFERENCES payments(payment_id, order_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_payment_receipts_correction_original
                FOREIGN KEY (corrects_receipt_id, payment_id, order_id)
                REFERENCES payment_receipts(receipt_id, payment_id, order_id)
                ON DELETE RESTRICT,
            ADD CONSTRAINT ck_payment_receipts_movement CHECK (
                (
                    source <> 'payment_correction'
                    AND amount > 0
                    AND corrects_receipt_id IS NULL
                    AND correction_reason IS NULL
                ) OR (
                    source = 'payment_correction'
                    AND amount < 0
                    AND corrects_receipt_id IS NOT NULL
                    AND NULLIF(BTRIM(correction_reason), '') IS NOT NULL
                    AND NULLIF(BTRIM(actor), '') IS NOT NULL
                    AND corrects_receipt_id <> receipt_id
                )
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX idx_payment_receipts_order_received
            ON payment_receipts(order_id, received_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX idx_payment_receipts_payment_order
            ON payment_receipts(payment_id, order_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX idx_payment_receipts_correction_original
            ON payment_receipts(corrects_receipt_id, payment_id, order_id)
            WHERE corrects_receipt_id IS NOT NULL
            """
        )
        _create_payment_receipt_triggers(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (74,),
        )
        current_version = 74
    if current_version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is unsupported; "
            f"this installation requires version {SCHEMA_VERSION}."
        )
    validate_current_schema(connection, SCHEMA_VERSION)
