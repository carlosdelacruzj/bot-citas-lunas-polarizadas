from __future__ import annotations

from datetime import UTC, datetime

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
)
from appointment_bot.db.migration_steps.order_schema import (
    _create_observer_window_metrics_schema,
    _create_order_checks_schema,
)
from appointment_bot.db.migration_steps.post_appointment_schema import (
    _create_post_appointment_schema,
)
from appointment_bot.db.migration_steps.reminder_schema import (
    _create_appointment_reminder_lead_days_schema,
    _create_appointment_reminder_schema,
    _create_current_appointment_reminder_control_schema,
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
)
from appointment_bot.db.migration_steps.whatsapp_schema import (
    _create_whatsapp_automation_jobs_schema,
    _create_whatsapp_followup_messages_schema,
    _create_whatsapp_messages_schema,
)
from appointment_bot.db.migration_steps.worker_schema import (
    _create_remote_control_audit_schema,
    _create_telegram_alert_outbox_schema,
    _create_worker_commands_schema,
)


def create_current_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id integer PRIMARY KEY CHECK (id = 1),
            version integer NOT NULL CHECK (version >= 0)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS applicants (
            applicant_id text PRIMARY KEY,
            document_number text NOT NULL UNIQUE,
            full_name text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS portal_accounts (
            portal_account_id text PRIMARY KEY,
            applicant_id text NOT NULL REFERENCES applicants(applicant_id) ON DELETE CASCADE,
            username text NOT NULL UNIQUE,
            document_type text NOT NULL DEFAULT 'dni' CHECK (
                document_type IN ('dni', 'foreign_resident_card')
            ),
            password text NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT uq_portal_accounts_identity UNIQUE (portal_account_id, applicant_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_contacts (
            contact_id text PRIMARY KEY,
            phone text UNIQUE,
            username text,
            display_name text,
            contact_source text NOT NULL DEFAULT 'whatsapp',
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_whatsapp_contacts_username_lower
        ON whatsapp_contacts(lower(username))
        WHERE username IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS applicant_contacts (
            applicant_id text NOT NULL REFERENCES applicants(applicant_id) ON DELETE CASCADE,
            contact_id text NOT NULL REFERENCES whatsapp_contacts(contact_id) ON DELETE CASCADE,
            is_primary boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            PRIMARY KEY (applicant_id, contact_id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_applicant_contacts_primary
        ON applicant_contacts(applicant_id)
        WHERE is_primary = true
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS service_orders (
            order_id text PRIMARY KEY,
            applicant_id text NOT NULL REFERENCES applicants(applicant_id) ON DELETE CASCADE,
            portal_account_id text NOT NULL REFERENCES portal_accounts(portal_account_id)
                ON DELETE CASCADE,
            priority integer NOT NULL DEFAULT 0 CHECK (priority >= 0),
            charge_required boolean NOT NULL DEFAULT true,
            service_type text NOT NULL DEFAULT 'standard',
            reservation_price numeric(12, 2) NOT NULL DEFAULT 50.00 CHECK (
                reservation_price > 0
            ),
            service_package text NOT NULL DEFAULT 'standard' CHECK (
                service_package IN ('standard', 'restricted', 'integral', 'custom')
            ),
            official_fee_amount numeric(12, 2) NOT NULL DEFAULT 0 CHECK (
                official_fee_amount >= 0 AND official_fee_amount <= reservation_price
            ),
            initial_payment_amount numeric(12, 2) NOT NULL DEFAULT 0 CHECK (
                initial_payment_amount >= 0 AND initial_payment_amount <= reservation_price
            ),
            CONSTRAINT ck_service_orders_service_type CHECK (
                service_type IN ('standard', 'selected_weekday', 'custom')
            ),
            CONSTRAINT ck_service_orders_integral_terms CHECK (
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
            ),
            acquisition_source text,
            acquisition_source_origin text CHECK (
                acquisition_source_origin IS NULL OR acquisition_source_origin IN (
                    'order_creation', 'historical_backfill'
                )
            ),
            minimum_hour integer CHECK (
                minimum_hour IS NULL OR (minimum_hour >= 0 AND minimum_hour <= 23)
            ),
            minimum_date date,
            maximum_date date,
            allowed_weekdays smallint[] CHECK (
                allowed_weekdays IS NULL OR allowed_weekdays <@ ARRAY[1,2,3,4,5,6,7]::smallint[]
            ),
            excluded_date_ranges jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
                jsonb_typeof(excluded_date_ranges) = 'array'
            ),
            parent_order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            program_expediente text,
            program_plate text,
            closure_reason text CHECK (
                closure_reason IS NULL OR closure_reason IN (
                    'completed_by_us',
                    'family_no_charge',
                    'client_withdrew',
                    'external_slot',
                    'duplicate',
                    'not_serviceable',
                    'uncollectible'
                )
            ),
            closure_note text,
            closed_at timestamptz,
            status text NOT NULL DEFAULT 'ready' CHECK (
                status IN ('ready', 'paused', 'reserved_payment_pending', 'paid', 'archived')
            ),
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            lease_owner text,
            lease_expires_at timestamptz,
            CONSTRAINT fk_service_orders_account_applicant
                FOREIGN KEY (portal_account_id, applicant_id)
                REFERENCES portal_accounts(portal_account_id, applicant_id) ON DELETE CASCADE,
            CONSTRAINT ck_service_orders_lease_pair CHECK (
                (lease_owner IS NULL) = (lease_expires_at IS NULL)
            ),
            CONSTRAINT ck_service_orders_reservation_date_range CHECK (
                maximum_date IS NULL OR minimum_date IS NULL OR maximum_date >= minimum_date
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_service_orders_claimable
        ON service_orders(status, priority DESC, created_at ASC, lease_expires_at)
        WHERE status = 'ready'
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_service_orders_queue
        ON service_orders(status, priority DESC, created_at ASC)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS order_state (
            order_id text PRIMARY KEY REFERENCES service_orders(order_id) ON DELETE CASCADE,
            last_status text CHECK (
                last_status IS NULL OR last_status IN (
                    'available', 'completed', 'error', 'partial', 'paused', 'registered',
                    'reservation_unconfirmed', 'skipped', 'unavailable', 'unknown',
                    'programmed', 'submission_intent', 'submission_pending'
                )
            ),
            last_message text,
            consecutive_errors integer NOT NULL DEFAULT 0 CHECK (consecutive_errors >= 0),
            credential_failures integer NOT NULL DEFAULT 0 CHECK (credential_failures >= 0),
            next_allowed_at timestamptz,
            last_run_at timestamptz,
            last_success_at timestamptz,
            programmed_at timestamptz,
            program_listing jsonb,
            preflight_status text NOT NULL DEFAULT 'not_required' CHECK (
                preflight_status IN ('not_required', 'pending', 'running', 'validated', 'failed')
            ),
            preflight_message text,
            preflight_started_at timestamptz,
            preflight_validated_at timestamptz,
            preflight_details jsonb,
            preflight_cycle integer NOT NULL DEFAULT 0 CHECK (preflight_cycle >= 0)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id text PRIMARY KEY,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            status text NOT NULL CHECK (
                status IN (
                    'available', 'completed', 'error', 'partial', 'paused', 'registered',
                    'reservation_unconfirmed', 'skipped', 'unavailable', 'unknown'
                )
            ),
            message text NOT NULL,
            exit_code integer NOT NULL,
            started_at timestamptz NOT NULL,
            finished_at timestamptz NOT NULL,
            duration_seconds double precision NOT NULL CHECK (duration_seconds >= 0),
            reservation_attempted boolean NOT NULL DEFAULT false,
            reservation_confirmed boolean NOT NULL DEFAULT false,
            details_json jsonb,
            screenshot_path text,
            created_at timestamptz NOT NULL,
            CONSTRAINT uq_runs_order UNIQUE (run_id, order_id),
            CONSTRAINT ck_runs_timestamps CHECK (finished_at >= started_at),
            CONSTRAINT ck_runs_reservation_flags CHECK (
                NOT reservation_confirmed OR reservation_attempted
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_runs_order_started
        ON runs(order_id, started_at DESC)
        """
    )
    _create_order_checks_schema(connection)
    _create_observer_window_metrics_schema(connection)
    _create_reservation_attempts_schema(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS run_screenshots (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            path text NOT NULL,
            created_at timestamptz NOT NULL,
            UNIQUE (run_id, path)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reservations (
            reservation_id text PRIMARY KEY,
            order_id text NOT NULL REFERENCES service_orders(order_id) ON DELETE CASCADE,
            run_id text,
            status text NOT NULL CHECK (status IN ('confirmed', 'unconfirmed')),
            site text,
            appointment_date text,
            appointment_hour text,
            slots text,
            evidence_path text,
            details_json jsonb,
            reserved_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT uq_reservations_order UNIQUE (reservation_id, order_id),
            CONSTRAINT fk_reservations_run_order
                FOREIGN KEY (run_id, order_id)
                REFERENCES runs(run_id, order_id) ON DELETE SET NULL (run_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reservations_order_created
        ON reservations(order_id, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            payment_id text PRIMARY KEY,
            order_id text NOT NULL REFERENCES service_orders(order_id) ON DELETE CASCADE,
            reservation_id text,
            status text NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'paid', 'written_off')
            ),
            amount_agreed numeric(12, 2),
            amount_paid numeric(12, 2),
            currency text NOT NULL DEFAULT 'PEN',
            paid_at timestamptz,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT payments_non_negative_amounts CHECK (
                (amount_agreed IS NULL OR amount_agreed >= 0)
                AND (amount_paid IS NULL OR amount_paid >= 0)
            ),
            CONSTRAINT uq_payments_payment_order UNIQUE (payment_id, order_id),
            CONSTRAINT fk_payments_reservation_order
                FOREIGN KEY (reservation_id, order_id)
                REFERENCES reservations(reservation_id, order_id)
                ON DELETE SET NULL (reservation_id),
            CONSTRAINT ck_payments_paid_fields CHECK (
                status <> 'paid' OR (amount_paid IS NOT NULL AND paid_at IS NOT NULL)
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_payments_order_created
        ON payments(order_id, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_receipts (
            receipt_id text PRIMARY KEY,
            payment_id text NOT NULL,
            order_id text NOT NULL,
            amount numeric(12, 2) NOT NULL,
            received_at timestamptz NOT NULL,
            source text NOT NULL,
            actor text,
            corrects_receipt_id text,
            correction_reason text,
            created_at timestamptz NOT NULL,
            CONSTRAINT uq_payment_receipts_identity_payment_order
                UNIQUE (receipt_id, payment_id, order_id),
            CONSTRAINT fk_payment_receipts_payment_order
                FOREIGN KEY (payment_id, order_id)
                REFERENCES payments(payment_id, order_id) ON DELETE RESTRICT,
            CONSTRAINT fk_payment_receipts_correction_original
                FOREIGN KEY (corrects_receipt_id, payment_id, order_id)
                REFERENCES payment_receipts(receipt_id, payment_id, order_id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_payment_receipts_movement CHECK (
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
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_payment_receipts_received
        ON payment_receipts(received_at, order_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_payment_receipts_order_received
        ON payment_receipts(order_id, received_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_payment_receipts_payment_order
        ON payment_receipts(payment_id, order_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_payment_receipts_correction_original
        ON payment_receipts(corrects_receipt_id, payment_id, order_id)
        WHERE corrects_receipt_id IS NOT NULL
        """
    )
    _create_payment_receipt_triggers(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_state (
            id integer PRIMARY KEY CHECK (id = 1),
            phase text NOT NULL DEFAULT 'stopped',
            paused boolean NOT NULL DEFAULT false,
            current_order_id text CONSTRAINT fk_worker_state_current_order
                REFERENCES service_orders(order_id) ON DELETE SET NULL,
            masked_account text,
            session_started_at timestamptz,
            last_check_at timestamptz,
            next_check_at timestamptz,
            confirmed_reservations integer NOT NULL DEFAULT 0 CHECK (confirmed_reservations >= 0),
            consecutive_errors integer NOT NULL DEFAULT 0 CHECK (consecutive_errors >= 0),
            last_error text,
            availability_signature text,
            owner_token text,
            updated_at timestamptz NOT NULL,
            lease_expires_at timestamptz
        )
        """
    )
    connection.execute(
        """
        INSERT INTO worker_state (id, updated_at)
        VALUES (1, %s)
        ON CONFLICT DO NOTHING
        """,
        (datetime.now(UTC),),
    )
    _create_worker_commands_schema(connection)
    _create_remote_control_audit_schema(connection)
    _create_finance_schema(connection)
    _create_finance_month_closure_schema(connection)
    _create_whatsapp_messages_schema(connection)
    _create_whatsapp_followup_messages_schema(connection)
    _create_whatsapp_automation_jobs_schema(connection)
    _create_appointment_reminder_schema(connection)
    _create_current_appointment_reminder_control_schema(connection)
    _create_appointment_reminder_lead_days_schema(connection)
    _create_whatsapp_message_template_schema(connection)
    _create_whatsapp_automation_template_trace_schema(connection)
    _create_whatsapp_message_template_trace_schema(connection)
    _create_whatsapp_followup_template_trace_schema(connection)
    _freeze_historical_whatsapp_followup_text(connection)
    _create_captcha_shadow_outbox_schema(connection)
    _create_telegram_alert_outbox_schema(connection)
    _create_captcha_sampling_control_schema(connection)
    _create_captcha_authority_schema(connection)
    _create_post_appointment_schema(connection)
    _create_reservation_program_identity_schema(connection)
    _create_opportunity_observability_schema(connection)
