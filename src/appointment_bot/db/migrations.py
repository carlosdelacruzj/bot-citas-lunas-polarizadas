from __future__ import annotations

import json
from datetime import UTC, datetime

from psycopg import Connection

from appointment_bot.core.whatsapp_message_templates import (
    MAX_TEMPLATE_LENGTH,
    WHATSAPP_TEMPLATE_DEFINITIONS,
)

SCHEMA_VERSION = 71
_MIGRATION_LOCK_ID = 1_047_296_811


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
        CREATE INDEX IF NOT EXISTS idx_payment_receipts_received
        ON payment_receipts(received_at, order_id)
        """
    )
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


def _create_reservation_program_identity_schema(connection: Connection) -> None:
    connection.execute(
        """
        ALTER TABLE post_appointment_stage_snapshots
        ADD COLUMN IF NOT EXISTS message_text text
        """
    )
    connection.execute(
        """
        ALTER TABLE reservations
        ADD COLUMN IF NOT EXISTS program_expediente text,
        ADD COLUMN IF NOT EXISTS program_plate text
        """
    )
    connection.execute(
        """
        UPDATE reservations r
        SET program_expediente = COALESCE(
                r.program_expediente,
                NULLIF(r.details_json ->> 'program_expediente', ''),
                so.program_expediente
            ),
            program_plate = COALESCE(
                r.program_plate,
                NULLIF(r.details_json ->> 'program_plate', ''),
                so.program_plate
            )
        FROM service_orders so
        WHERE so.order_id = r.order_id
          AND (r.program_expediente IS NULL OR r.program_plate IS NULL)
        """
    )
    connection.execute(
        """
        WITH pending_programs AS (
            SELECT r.reservation_id,
                   row_data ->> 'expediente' AS program_expediente,
                   row_data ->> 'placa' AS program_plate,
                   count(*) OVER (PARTITION BY r.reservation_id) AS pending_count
            FROM reservations r
            JOIN order_state os ON os.order_id = r.order_id
            CROSS JOIN LATERAL jsonb_array_elements(
                COALESCE(
                    os.program_listing -> 'details' -> 'rows',
                    os.program_listing -> 'rows',
                    '[]'::jsonb
                )
            ) row_data
            WHERE r.status = 'confirmed'
              AND r.program_expediente IS NULL
              AND r.program_plate IS NULL
              AND lower(COALESCE(row_data ->> 'status', '')) = 'pendiente'
        )
        UPDATE reservations r
        SET program_expediente = NULLIF(candidate.program_expediente, ''),
            program_plate = NULLIF(candidate.program_plate, '')
        FROM pending_programs candidate
        WHERE candidate.reservation_id = r.reservation_id
          AND candidate.pending_count = 1
        """
    )
    connection.execute(
        """
        WITH latest_reservations AS (
            SELECT DISTINCT ON (r.order_id)
                   r.order_id, r.program_expediente, r.program_plate, r.updated_at
            FROM reservations r
            WHERE r.status = 'confirmed'
              AND (r.program_expediente IS NOT NULL OR r.program_plate IS NOT NULL)
            ORDER BY r.order_id, r.created_at DESC
        )
        UPDATE service_orders so
        SET program_expediente = reservation.program_expediente,
            program_plate = reservation.program_plate,
            updated_at = GREATEST(so.updated_at, reservation.updated_at)
        FROM latest_reservations reservation
        WHERE so.program_expediente IS NULL
          AND so.program_plate IS NULL
          AND reservation.order_id = so.order_id
        """
    )
    connection.execute(
        """
        UPDATE service_orders parent
        SET status = 'archived', updated_at = CURRENT_TIMESTAMP
        WHERE parent.status IN ('ready', 'paused')
          AND EXISTS (
              SELECT 1 FROM service_orders child
              WHERE child.parent_order_id = parent.order_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM reservations own_reservation
              WHERE own_reservation.order_id = parent.order_id
          )
        """
    )


def _create_post_appointment_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS post_appointment_reviews (
            review_id text PRIMARY KEY,
            order_id text NOT NULL REFERENCES service_orders(order_id) ON DELETE CASCADE,
            access_status text NOT NULL CHECK (
                access_status IN (
                    'success', 'invalid_credentials', 'workflow_unavailable', 'portal_error'
                )
            ),
            outcome text NOT NULL CHECK (
                outcome IN (
                    'upcoming', 'awaiting_update', 'in_progress', 'completed',
                    'observation_with_progress', 'observation_no_progress',
                    'access_lost', 'portal_unavailable', 'review_required'
                )
            ),
            appointment_date date,
            appointment_hour text,
            stage_count integer NOT NULL DEFAULT 0 CHECK (stage_count >= 0),
            observation_count integer NOT NULL DEFAULT 0 CHECK (observation_count >= 0),
            later_progress_observed boolean NOT NULL DEFAULT false,
            error_code text,
            error_message text,
            started_at timestamptz NOT NULL,
            finished_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL,
            CONSTRAINT ck_post_appointment_reviews_timestamps CHECK (
                finished_at >= started_at
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_post_appointment_reviews_order_finished
        ON post_appointment_reviews(order_id, finished_at DESC)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS post_appointment_stage_snapshots (
            review_id text NOT NULL REFERENCES post_appointment_reviews(review_id)
                ON DELETE CASCADE,
            stage_index integer NOT NULL CHECK (stage_index >= 0),
            stage_key text NOT NULL,
            stage_label text NOT NULL,
            stage_date date,
            stage_hour text,
            status_text text,
            message_present boolean NOT NULL DEFAULT false,
            message_text text,
            message_class text NOT NULL DEFAULT 'none' CHECK (
                message_class IN ('none', 'ok', 'observation', 'unknown')
            ),
            created_at timestamptz NOT NULL,
            PRIMARY KEY (review_id, stage_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS post_appointment_automatic_reviews (
            service_date date NOT NULL,
            reservation_id text NOT NULL REFERENCES reservations(reservation_id)
                ON DELETE CASCADE,
            order_id text NOT NULL REFERENCES service_orders(order_id) ON DELETE CASCADE,
            status text NOT NULL CHECK (
                status IN ('running', 'completed', 'failed', 'skipped')
            ),
            review_id text REFERENCES post_appointment_reviews(review_id) ON DELETE SET NULL,
            error_code text,
            error_message text,
            claimed_at timestamptz NOT NULL,
            finished_at timestamptz,
            PRIMARY KEY (service_date, reservation_id),
            CONSTRAINT ck_post_appointment_automatic_review_finished CHECK (
                (status = 'running' AND finished_at IS NULL)
                OR (status <> 'running' AND finished_at IS NOT NULL)
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_post_appointment_automatic_reviews_status
        ON post_appointment_automatic_reviews(service_date, status, claimed_at)
        """
    )


def _create_captcha_sampling_control_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS captcha_sampling_control (
            id integer PRIMARY KEY CHECK (id = 1),
            enabled boolean NOT NULL DEFAULT false,
            sample_limit integer NOT NULL DEFAULT 10 CHECK (
                sample_limit BETWEEN 2 AND 50
            ),
            updated_at timestamptz NOT NULL,
            updated_by text NOT NULL DEFAULT 'system'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO captcha_sampling_control (
            id, enabled, sample_limit, updated_at, updated_by
        )
        VALUES (1, false, 10, %s, 'migration')
        ON CONFLICT DO NOTHING
        """,
        (datetime.now(UTC),),
    )


def _create_captcha_authority_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS captcha_authority_control (
            id integer PRIMARY KEY CHECK (id = 1),
            mode text NOT NULL DEFAULT '2captcha' CHECK (
                mode IN ('2captcha', 'canary')
            ),
            canary_limit integer NOT NULL DEFAULT 20 CHECK (
                canary_limit BETWEEN 1 AND 100
            ),
            local_decisions integer NOT NULL DEFAULT 0 CHECK (local_decisions >= 0),
            local_confirmed integer NOT NULL DEFAULT 0 CHECK (local_confirmed >= 0),
            local_rejected integer NOT NULL DEFAULT 0 CHECK (local_rejected >= 0),
            fallback_decisions integer NOT NULL DEFAULT 0 CHECK (
                fallback_decisions >= 0
            ),
            min_char_confidence double precision NOT NULL DEFAULT 0.60 CHECK (
                min_char_confidence BETWEEN 0 AND 1
            ),
            sequence_confidence_product double precision NOT NULL DEFAULT 0.60 CHECK (
                sequence_confidence_product BETWEEN 0 AND 1
            ),
            timeout_ms integer NOT NULL DEFAULT 500 CHECK (timeout_ms BETWEEN 100 AND 2000),
            circuit_state text NOT NULL DEFAULT 'closed' CHECK (
                circuit_state IN ('closed', 'open')
            ),
            circuit_reason text,
            circuit_opened_at timestamptz,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_by text NOT NULL DEFAULT 'migration',
            activated_at timestamptz,
            CONSTRAINT ck_captcha_authority_circuit CHECK (
                circuit_state = 'closed'
                OR (circuit_reason IS NOT NULL AND circuit_opened_at IS NOT NULL)
            )
        )
        """
    )
    connection.execute(
        """
        INSERT INTO captcha_authority_control (id)
        VALUES (1)
        ON CONFLICT DO NOTHING
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS captcha_authority_decisions (
            decision_id text PRIMARY KEY,
            event_id text NOT NULL UNIQUE,
            run_id text,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            attempt_number integer NOT NULL CHECK (attempt_number > 0),
            source text NOT NULL CHECK (source IN ('v6', '2captcha')),
            fallback_reason text,
            prediction_sha256 text CHECK (
                prediction_sha256 IS NULL OR prediction_sha256 ~ '^[a-f0-9]{64}$'
            ),
            mean_confidence double precision,
            min_char_confidence double precision,
            sequence_confidence_product double precision,
            inference_ms double precision,
            request_ms double precision,
            portal_outcome text,
            portal_accepted boolean,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at timestamptz,
            CONSTRAINT ck_captcha_authority_decision_resolution CHECK (
                (resolved_at IS NULL AND portal_outcome IS NULL)
                OR (resolved_at IS NOT NULL AND portal_outcome IS NOT NULL)
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_captcha_authority_decisions_created
        ON captcha_authority_decisions(created_at DESC)
        """
    )


def _create_opportunity_observability_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_bursts (
            burst_id text PRIMARY KEY,
            detector_order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            detector_run_id text,
            status text NOT NULL CHECK (
                status IN ('running', 'draining', 'closed', 'aborted')
            ),
            started_at timestamptz NOT NULL,
            admission_deadline_at timestamptz NOT NULL,
            finished_at timestamptz,
            completion_reason text,
            circuit_reason text,
            opportunities_json jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
                jsonb_typeof(opportunities_json) = 'array'
            ),
            config_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (
                jsonb_typeof(config_json) = 'object'
            ),
            configured_max_sessions smallint NOT NULL CHECK (
                configured_max_sessions BETWEEN 1 AND 2
            ),
            configured_max_clients integer NOT NULL CHECK (configured_max_clients >= 0),
            max_active_sessions smallint NOT NULL DEFAULT 1 CHECK (
                max_active_sessions BETWEEN 0 AND 2
            ),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_opportunity_bursts_timestamps CHECK (
                admission_deadline_at >= started_at
                AND (finished_at IS NULL OR finished_at >= started_at)
            ),
            CONSTRAINT ck_opportunity_bursts_finished CHECK (
                (status IN ('running', 'draining') AND finished_at IS NULL)
                OR (status IN ('closed', 'aborted') AND finished_at IS NOT NULL)
            )
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_opportunity_bursts_active
        ON opportunity_bursts ((true))
        WHERE status IN ('running', 'draining')
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_opportunity_bursts_started
        ON opportunity_bursts(started_at DESC, burst_id DESC)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_burst_candidates (
            candidate_id text PRIMARY KEY,
            burst_id text NOT NULL REFERENCES opportunity_bursts(burst_id) ON DELETE CASCADE,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            queue_position integer NOT NULL CHECK (queue_position > 0),
            priority_snapshot integer NOT NULL CHECK (priority_snapshot >= 0),
            selection_source text NOT NULL DEFAULT 'ranked' CHECK (
                selection_source IN ('ranked', 'preferred')
            ),
            compatible_opportunities jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
                jsonb_typeof(compatible_opportunities) = 'array'
            ),
            state text NOT NULL DEFAULT 'queued' CHECK (
                state IN ('queued', 'admitted', 'skipped', 'completed', 'cancelled')
            ),
            skip_reason text,
            discovered_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            admitted_at timestamptz,
            finished_at timestamptz,
            CONSTRAINT uq_opportunity_burst_candidate_position
                UNIQUE (burst_id, queue_position),
            CONSTRAINT ck_opportunity_burst_candidate_timestamps CHECK (
                admitted_at IS NULL OR admitted_at >= discovered_at
            )
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_opportunity_burst_candidates_order
        ON opportunity_burst_candidates(burst_id, order_id)
        WHERE order_id IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_opportunity_burst_candidates_state
        ON opportunity_burst_candidates(burst_id, state, queue_position)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_burst_executions (
            execution_id text PRIMARY KEY,
            burst_id text NOT NULL REFERENCES opportunity_bursts(burst_id) ON DELETE CASCADE,
            candidate_id text REFERENCES opportunity_burst_candidates(candidate_id)
                ON DELETE SET NULL,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            run_id text,
            role text NOT NULL CHECK (role IN ('detector', 'auxiliary')),
            execution_position integer NOT NULL CHECK (execution_position >= 0),
            previous_candidate_id text REFERENCES opportunity_burst_candidates(candidate_id)
                ON DELETE SET NULL,
            next_candidate_id text REFERENCES opportunity_burst_candidates(candidate_id)
                ON DELETE SET NULL,
            state text NOT NULL DEFAULT 'scheduled' CHECK (
                state IN ('scheduled', 'claiming', 'running', 'finished', 'skipped')
            ),
            claim_acquired boolean,
            lease_lost boolean NOT NULL DEFAULT false,
            started_at timestamptz,
            first_read_at timestamptz,
            captcha_started_at timestamptz,
            submitted_at timestamptz,
            confirmed_at timestamptz,
            finished_at timestamptz,
            result_status text,
            exit_code integer,
            exit_cause text,
            reservation_timing_json jsonb CHECK (
                reservation_timing_json IS NULL
                OR jsonb_typeof(reservation_timing_json) = 'object'
            ),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_opportunity_burst_execution_role CHECK (
                (role = 'detector' AND candidate_id IS NULL AND execution_position = 0)
                OR (role = 'auxiliary' AND candidate_id IS NOT NULL AND execution_position > 0)
            ),
            CONSTRAINT ck_opportunity_burst_execution_finished CHECK (
                state NOT IN ('finished', 'skipped') OR finished_at IS NOT NULL
            ),
            CONSTRAINT ck_opportunity_burst_execution_timestamps CHECK (
                finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at
            )
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_opportunity_burst_detector
        ON opportunity_burst_executions(burst_id)
        WHERE role = 'detector'
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_opportunity_burst_execution_candidate
        ON opportunity_burst_executions(candidate_id)
        WHERE candidate_id IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_opportunity_burst_executions_position
        ON opportunity_burst_executions(burst_id, execution_position)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_opportunity_burst_executions_order
        ON opportunity_burst_executions(order_id, started_at DESC)
        WHERE order_id IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS slot_lost_reobservation_events (
            event_id text PRIMARY KEY,
            event_key text NOT NULL UNIQUE,
            reobservation_id text NOT NULL,
            sequence integer NOT NULL CHECK (sequence >= 0),
            burst_id text REFERENCES opportunity_bursts(burst_id) ON DELETE SET NULL,
            execution_id text REFERENCES opportunity_burst_executions(execution_id)
                ON DELETE SET NULL,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            run_id text,
            event_type text NOT NULL CHECK (
                event_type IN (
                    'started', 'slot_lost_resolved', 'observation',
                    'second_attempt_intent', 'second_attempt_resolved', 'finished'
                )
            ),
            original_attempt_id text REFERENCES reservation_attempts(attempt_id)
                ON DELETE SET NULL,
            second_attempt_id text REFERENCES reservation_attempts(attempt_id)
                ON DELETE SET NULL,
            attempt_number integer CHECK (attempt_number IS NULL OR attempt_number >= 0),
            mode text,
            observed_status text,
            outcome text,
            duration_ms integer CHECK (duration_ms IS NULL OR duration_ms >= 0),
            occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            details_json jsonb CHECK (
                details_json IS NULL OR jsonb_typeof(details_json) = 'object'
            ),
            UNIQUE (reobservation_id, sequence)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_slot_lost_reobservation_sequence
        ON slot_lost_reobservation_events(reobservation_id, sequence)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_slot_lost_reobservation_burst
        ON slot_lost_reobservation_events(burst_id, occurred_at)
        WHERE burst_id IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_runtime_control (
            id integer PRIMARY KEY CHECK (id = 1),
            burst_mode text NOT NULL DEFAULT 'enabled'
                CONSTRAINT ck_opportunity_runtime_control_burst_mode CHECK (
                    burst_mode IN ('enabled', 'disabled', 'draining')
                ),
            obs007_mode text NOT NULL DEFAULT 'enabled'
                CONSTRAINT ck_opportunity_runtime_control_obs007_mode CHECK (
                    obs007_mode IN ('enabled', 'disabled')
                ),
            revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
            applied_revision bigint NOT NULL DEFAULT 0 CHECK (
                applied_revision >= 0 AND applied_revision <= revision
            ),
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_by text NOT NULL DEFAULT 'migration',
            applied_at timestamptz,
            applied_by_worker text,
            circuit_state text NOT NULL DEFAULT 'closed' CHECK (
                circuit_state IN ('closed', 'open')
            ),
            circuit_reason text,
            circuit_opened_at timestamptz,
            circuit_reset_at timestamptz,
            circuit_reset_by text,
            CONSTRAINT ck_opportunity_runtime_control_circuit CHECK (
                (circuit_state = 'closed')
                OR (circuit_state = 'open' AND circuit_reason IS NOT NULL
                    AND circuit_opened_at IS NOT NULL)
            )
        )
        """
    )
    connection.execute(
        """
        INSERT INTO opportunity_runtime_control (id)
        VALUES (1)
        ON CONFLICT DO NOTHING
        """
    )


def _validate_current_schema(connection: Connection) -> None:
    required_tables = {
        "schema_version",
        "applicants",
        "portal_accounts",
        "whatsapp_contacts",
        "applicant_contacts",
        "service_orders",
        "order_state",
        "runs",
        "order_checks",
        "observer_window_metrics",
        "reservation_attempts",
        "run_screenshots",
        "reservations",
        "payments",
        "payment_receipts",
        "worker_state",
        "worker_commands",
        "remote_control_audit",
        "finance_categories",
        "finance_entries",
        "finance_month_closures",
        "payment_amount_reconciliations",
        "whatsapp_messages",
        "whatsapp_followup_messages",
        "whatsapp_automation_jobs",
        "appointment_reminder_days",
        "appointment_reminder_control",
        "whatsapp_message_templates",
        "whatsapp_message_template_versions",
        "captcha_shadow_outbox",
        "telegram_alert_outbox",
        "captcha_sampling_control",
        "captcha_authority_control",
        "captcha_authority_decisions",
        "post_appointment_reviews",
        "post_appointment_stage_snapshots",
        "post_appointment_automatic_reviews",
        "opportunity_bursts",
        "opportunity_burst_candidates",
        "opportunity_burst_executions",
        "slot_lost_reobservation_events",
        "opportunity_runtime_control",
    }
    tables = {
        row["table_name"]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
        )
    }
    required_columns = {
        ("schema_version", "version"),
        ("whatsapp_contacts", "contact_source"),
        ("whatsapp_contacts", "username"),
        ("portal_accounts", "applicant_id"),
        ("portal_accounts", "password"),
        ("portal_accounts", "document_type"),
        ("service_orders", "status"),
        ("service_orders", "service_type"),
        ("service_orders", "reservation_price"),
        ("service_orders", "service_package"),
        ("service_orders", "official_fee_amount"),
        ("service_orders", "initial_payment_amount"),
        ("service_orders", "acquisition_source"),
        ("service_orders", "acquisition_source_origin"),
        ("service_orders", "minimum_hour"),
        ("service_orders", "minimum_date"),
        ("service_orders", "maximum_date"),
        ("service_orders", "allowed_weekdays"),
        ("service_orders", "excluded_date_ranges"),
        ("service_orders", "parent_order_id"),
        ("service_orders", "program_expediente"),
        ("service_orders", "program_plate"),
        ("service_orders", "closure_reason"),
        ("service_orders", "closure_note"),
        ("service_orders", "closed_at"),
        ("service_orders", "lease_owner"),
        ("service_orders", "lease_expires_at"),
        ("runs", "reservation_attempted"),
        ("runs", "reservation_confirmed"),
        ("order_checks", "checked_at"),
        ("order_state", "credential_failures"),
        ("order_state", "program_listing"),
        ("order_state", "preflight_status"),
        ("order_state", "preflight_message"),
        ("order_state", "preflight_started_at"),
        ("order_state", "preflight_validated_at"),
        ("order_state", "preflight_details"),
        ("order_state", "preflight_cycle"),
        ("reservation_attempts", "idempotency_key"),
        ("reservation_attempts", "status"),
        ("reservations", "run_id"),
        ("reservations", "status"),
        ("reservations", "appointment_day"),
        ("reservations", "program_expediente"),
        ("reservations", "program_plate"),
        ("payments", "reservation_id"),
        ("payments", "status"),
        ("worker_state", "current_order_id"),
        ("worker_state", "owner_token"),
        ("worker_state", "lease_expires_at"),
        ("worker_commands", "command"),
        ("worker_commands", "status"),
        ("worker_commands", "requested_at"),
        ("remote_control_audit", "actor"),
        ("remote_control_audit", "action"),
        ("remote_control_audit", "status"),
        ("remote_control_audit", "created_at"),
        ("finance_categories", "category_code"),
        ("finance_entries", "entry_kind"),
        ("finance_entries", "amount_original"),
        ("finance_entries", "amount_pen"),
        ("finance_entries", "status"),
        ("payment_receipts", "payment_id"),
        ("payment_receipts", "amount"),
        ("payment_receipts", "received_at"),
        ("finance_month_closures", "month_start"),
        ("finance_month_closures", "opening_prepaid_balance"),
        ("finance_month_closures", "closing_prepaid_balance"),
        ("finance_month_closures", "status"),
        ("finance_month_closures", "reconciled_at"),
        ("finance_month_closures", "reconciled_by"),
        ("payment_amount_reconciliations", "payment_id"),
        ("payment_amount_reconciliations", "resolution_type"),
        ("payment_amount_reconciliations", "reason"),
        ("payment_amount_reconciliations", "reconciled_by"),
        ("whatsapp_messages", "message_id"),
        ("whatsapp_messages", "recipient_phone"),
        ("whatsapp_messages", "recipient_username"),
        ("whatsapp_messages", "attachment_path"),
        ("whatsapp_messages", "payment_attachment_path"),
        ("whatsapp_messages", "status"),
        ("whatsapp_messages", "test_mode"),
        ("whatsapp_messages", "sent_at"),
        ("whatsapp_messages", "confirmation_template_key"),
        ("whatsapp_messages", "confirmation_template_revision"),
        ("whatsapp_messages", "payment_template_key"),
        ("whatsapp_messages", "payment_template_revision"),
        ("whatsapp_followup_messages", "message_id"),
        ("whatsapp_followup_messages", "recipient_phone"),
        ("whatsapp_followup_messages", "recipient_username"),
        ("whatsapp_followup_messages", "steps"),
        ("whatsapp_followup_messages", "status"),
        ("whatsapp_followup_messages", "test_mode"),
        ("whatsapp_followup_messages", "sent_at"),
        ("whatsapp_followup_messages", "message_text"),
        ("whatsapp_followup_messages", "template_key"),
        ("whatsapp_followup_messages", "template_revision"),
        ("whatsapp_automation_jobs", "job_key"),
        ("whatsapp_automation_jobs", "order_id"),
        ("whatsapp_automation_jobs", "job_kind"),
        ("whatsapp_automation_jobs", "status"),
        ("whatsapp_automation_jobs", "attempt_count"),
        ("whatsapp_automation_jobs", "lease_expires_at"),
        ("whatsapp_automation_jobs", "next_attempt_at"),
        ("whatsapp_automation_jobs", "preflight_error"),
        ("whatsapp_automation_jobs", "preflight_alerted_at"),
        ("whatsapp_automation_jobs", "review_resolution"),
        ("whatsapp_automation_jobs", "review_note"),
        ("whatsapp_automation_jobs", "reviewed_at"),
        ("whatsapp_automation_jobs", "reviewed_by"),
        ("whatsapp_automation_jobs", "report_date"),
        ("whatsapp_automation_jobs", "recipient_phone"),
        ("whatsapp_automation_jobs", "recipient_username"),
        ("whatsapp_automation_jobs", "message_text"),
        ("whatsapp_automation_jobs", "publication_text"),
        ("whatsapp_automation_jobs", "attachment_paths"),
        ("whatsapp_automation_jobs", "registration_notice_type"),
        ("whatsapp_automation_jobs", "preflight_cycle"),
        ("whatsapp_automation_jobs", "reservation_id"),
        ("whatsapp_automation_jobs", "appointment_day"),
        ("whatsapp_automation_jobs", "priority"),
        ("whatsapp_automation_jobs", "template_key"),
        ("whatsapp_automation_jobs", "template_revision"),
        ("appointment_reminder_days", "service_date"),
        ("appointment_reminder_days", "appointment_day"),
        ("appointment_reminder_days", "status"),
        ("appointment_reminder_days", "last_reconciled_at"),
        ("appointment_reminder_control", "mode"),
        ("appointment_reminder_control", "lead_days"),
        ("appointment_reminder_control", "revision"),
        ("whatsapp_message_templates", "template_key"),
        ("whatsapp_message_templates", "message_template"),
        ("whatsapp_message_templates", "revision"),
        ("whatsapp_message_templates", "enabled"),
        ("whatsapp_message_templates", "updated_at"),
        ("whatsapp_message_templates", "updated_by"),
        ("whatsapp_message_template_versions", "template_key"),
        ("whatsapp_message_template_versions", "revision"),
        ("whatsapp_message_template_versions", "message_template"),
        ("whatsapp_message_template_versions", "created_at"),
        ("whatsapp_message_template_versions", "created_by"),
        ("captcha_shadow_outbox", "event_key"),
        ("captcha_shadow_outbox", "event_id"),
        ("captcha_shadow_outbox", "sequence"),
        ("captcha_shadow_outbox", "status"),
        ("captcha_shadow_outbox", "next_attempt_at"),
        ("telegram_alert_outbox", "dedupe_key"),
        ("telegram_alert_outbox", "payload"),
        ("telegram_alert_outbox", "status"),
        ("telegram_alert_outbox", "attempt_count"),
        ("telegram_alert_outbox", "next_attempt_at"),
        ("captcha_sampling_control", "enabled"),
        ("captcha_sampling_control", "sample_limit"),
        ("captcha_sampling_control", "updated_at"),
        ("captcha_sampling_control", "updated_by"),
        ("captcha_authority_control", "mode"),
        ("captcha_authority_control", "canary_limit"),
        ("captcha_authority_control", "local_decisions"),
        ("captcha_authority_control", "circuit_state"),
        ("captcha_authority_decisions", "event_id"),
        ("captcha_authority_decisions", "source"),
        ("captcha_authority_decisions", "portal_outcome"),
        ("post_appointment_reviews", "order_id"),
        ("post_appointment_reviews", "access_status"),
        ("post_appointment_reviews", "outcome"),
        ("post_appointment_reviews", "finished_at"),
        ("post_appointment_stage_snapshots", "review_id"),
        ("post_appointment_stage_snapshots", "stage_key"),
        ("post_appointment_stage_snapshots", "message_present"),
        ("post_appointment_stage_snapshots", "message_class"),
        ("post_appointment_stage_snapshots", "message_text"),
        ("post_appointment_automatic_reviews", "service_date"),
        ("post_appointment_automatic_reviews", "reservation_id"),
        ("post_appointment_automatic_reviews", "order_id"),
        ("post_appointment_automatic_reviews", "status"),
        ("post_appointment_automatic_reviews", "review_id"),
        ("post_appointment_automatic_reviews", "claimed_at"),
        ("post_appointment_automatic_reviews", "finished_at"),
        ("opportunity_bursts", "burst_id"),
        ("opportunity_bursts", "status"),
        ("opportunity_bursts", "admission_deadline_at"),
        ("opportunity_bursts", "max_active_sessions"),
        ("opportunity_burst_candidates", "candidate_id"),
        ("opportunity_burst_candidates", "queue_position"),
        ("opportunity_burst_candidates", "state"),
        ("opportunity_burst_executions", "execution_id"),
        ("opportunity_burst_executions", "role"),
        ("opportunity_burst_executions", "state"),
        ("opportunity_burst_executions", "first_read_at"),
        ("opportunity_burst_executions", "submitted_at"),
        ("slot_lost_reobservation_events", "event_key"),
        ("slot_lost_reobservation_events", "reobservation_id"),
        ("slot_lost_reobservation_events", "event_type"),
        ("slot_lost_reobservation_events", "original_attempt_id"),
        ("slot_lost_reobservation_events", "second_attempt_id"),
        ("opportunity_runtime_control", "burst_mode"),
        ("opportunity_runtime_control", "obs007_mode"),
        ("opportunity_runtime_control", "revision"),
        ("opportunity_runtime_control", "applied_revision"),
        ("opportunity_runtime_control", "circuit_state"),
    }
    columns = {
        (row["table_name"], row["column_name"])
        for row in connection.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema()"
        )
    }
    required_constraints = {
        "uq_portal_accounts_identity",
        "fk_service_orders_account_applicant",
        "ck_service_orders_lease_pair",
        "uq_runs_order",
        "ck_runs_timestamps",
        "ck_runs_reservation_flags",
        "uq_reservations_order",
        "fk_reservations_run_order",
        "fk_payments_reservation_order",
        "ck_payments_paid_fields",
        "fk_worker_state_current_order",
        "ck_whatsapp_messages_sent",
        "ck_whatsapp_messages_recipient",
        "ck_whatsapp_messages_confirmation_template_trace",
        "ck_whatsapp_messages_payment_template_trace",
        "ck_whatsapp_followup_messages_sent",
        "ck_whatsapp_followup_messages_recipient",
        "ck_whatsapp_followup_messages_template_trace",
        "ck_whatsapp_automation_job_review",
        "ck_whatsapp_automation_job_status",
        "ck_whatsapp_automation_job_attempt",
        "ck_whatsapp_automation_job_kind",
        "ck_whatsapp_automation_job_target",
        "fk_whatsapp_automation_jobs_reservation",
        "ck_appointment_reminder_control_lead_days",
        "ck_appointment_reminder_control_mode",
        "ck_appointment_reminder_day_target",
        "ck_post_appointment_reviews_timestamps",
        "ck_post_appointment_automatic_review_finished",
        "ck_opportunity_bursts_timestamps",
        "ck_opportunity_bursts_finished",
        "ck_opportunity_burst_candidate_timestamps",
        "ck_opportunity_burst_execution_role",
        "ck_opportunity_burst_execution_finished",
        "ck_opportunity_burst_execution_timestamps",
        "ck_opportunity_runtime_control_circuit",
        "ck_opportunity_runtime_control_burst_mode",
        "ck_opportunity_runtime_control_obs007_mode",
        "ck_captcha_authority_circuit",
        "ck_captcha_authority_decision_resolution",
        "ck_finance_month_closure_reconciliation",
        "ck_payment_amount_reconciliation_reason",
    }
    constraint_rows = connection.execute(
        "SELECT conname, convalidated FROM pg_constraint "
        "WHERE connamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())"
    ).fetchall()
    constraints = {row["conname"] for row in constraint_rows}
    indexes = {
        row["indexname"]
        for row in connection.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
        )
    }
    missing = sorted(required_tables - tables)
    missing.extend(f"{table}.{column}" for table, column in sorted(required_columns - columns))
    if "appointment_reminder_template_versions" in tables:
        missing.append("retired:appointment_reminder_template_versions")
    if ("appointment_reminder_control", "message_template") in columns:
        missing.append("retired:appointment_reminder_control.message_template")
    if (
        "whatsapp_followup_messages" in tables
        and ("whatsapp_followup_messages", "message_text") in columns
    ):
        empty_followup_text = connection.execute(
            """
            SELECT count(*) AS count
            FROM whatsapp_followup_messages
            WHERE NULLIF(BTRIM(message_text), '') IS NULL
            """
        ).fetchone()
        if empty_followup_text is None or int(empty_followup_text["count"]) != 0:
            missing.append("whatsapp_followup_messages.message_text empty")
    missing.extend(sorted(required_constraints - constraints))
    missing.extend(
        f"unvalidated:{row['conname']}"
        for row in constraint_rows
        if row["conname"] in required_constraints and not row["convalidated"]
    )
    if "idx_payments_order_created" not in indexes:
        missing.append("idx_payments_order_created")
    if "idx_order_checks_order_checked" not in indexes:
        missing.append("idx_order_checks_order_checked")
    if "idx_observer_window_metrics_date" not in indexes:
        missing.append("idx_observer_window_metrics_date")
    if "idx_reservation_attempts_order_created" not in indexes:
        missing.append("idx_reservation_attempts_order_created")
    if "uq_reservation_attempts_active_order" not in indexes:
        missing.append("uq_reservation_attempts_active_order")
    if "idx_worker_commands_pending" not in indexes:
        missing.append("idx_worker_commands_pending")
    if "idx_finance_entries_occurred" not in indexes:
        missing.append("idx_finance_entries_occurred")
    if "idx_whatsapp_messages_order_prepared" not in indexes:
        missing.append("idx_whatsapp_messages_order_prepared")
    if "idx_whatsapp_followup_messages_order_prepared" not in indexes:
        missing.append("idx_whatsapp_followup_messages_order_prepared")
    if "idx_whatsapp_automation_jobs_queued" not in indexes:
        missing.append("idx_whatsapp_automation_jobs_queued")
    if "uq_whatsapp_contacts_username_lower" not in indexes:
        missing.append("uq_whatsapp_contacts_username_lower")
    if "uq_whatsapp_automation_jobs_running" not in indexes:
        missing.append("uq_whatsapp_automation_jobs_running")
    if "idx_reservations_appointment_day_confirmed" not in indexes:
        missing.append("idx_reservations_appointment_day_confirmed")
    if "idx_whatsapp_automation_jobs_priority" not in indexes:
        missing.append("idx_whatsapp_automation_jobs_priority")
    if "idx_captcha_shadow_outbox_pending" not in indexes:
        missing.append("idx_captcha_shadow_outbox_pending")
    if "idx_telegram_alert_outbox_pending" not in indexes:
        missing.append("idx_telegram_alert_outbox_pending")
    if "idx_captcha_authority_decisions_created" not in indexes:
        missing.append("idx_captcha_authority_decisions_created")
    if "idx_post_appointment_reviews_order_finished" not in indexes:
        missing.append("idx_post_appointment_reviews_order_finished")
    if "idx_post_appointment_automatic_reviews_status" not in indexes:
        missing.append("idx_post_appointment_automatic_reviews_status")
    for index_name in (
        "uq_opportunity_bursts_active",
        "idx_opportunity_bursts_started",
        "uq_opportunity_burst_candidates_order",
        "idx_opportunity_burst_candidates_state",
        "uq_opportunity_burst_detector",
        "uq_opportunity_burst_execution_candidate",
        "idx_opportunity_burst_executions_position",
        "idx_opportunity_burst_executions_order",
        "idx_slot_lost_reobservation_sequence",
        "idx_slot_lost_reobservation_burst",
    ):
        if index_name not in indexes:
            missing.append(index_name)
    if missing:
        message = f"Database schema v{SCHEMA_VERSION} is incomplete: "
        raise RuntimeError(message + ", ".join(missing))


def _create_order_checks_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS order_checks (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            order_id text NOT NULL REFERENCES service_orders(order_id) ON DELETE CASCADE,
            status text NOT NULL,
            checked_at timestamptz NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_order_checks_order_checked
        ON order_checks(order_id, checked_at DESC)
        """
    )


def _create_observer_window_metrics_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS observer_window_metrics (
            metric_date date NOT NULL,
            window_label text NOT NULL,
            source text NOT NULL,
            status text NOT NULL,
            site text NOT NULL DEFAULT '',
            check_count integer NOT NULL DEFAULT 0 CHECK (check_count >= 0),
            error_count integer NOT NULL DEFAULT 0 CHECK (error_count >= 0),
            total_duration_seconds double precision NOT NULL DEFAULT 0
                CHECK (total_duration_seconds >= 0),
            first_seen_at timestamptz NOT NULL,
            last_seen_at timestamptz NOT NULL,
            last_order_id text,
            last_date text,
            last_hour text,
            PRIMARY KEY (metric_date, window_label, source, status, site)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_observer_window_metrics_date
        ON observer_window_metrics(metric_date DESC, window_label, source)
        """
    )


def _create_reservation_attempts_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reservation_attempts (
            attempt_id text PRIMARY KEY,
            order_id text NOT NULL REFERENCES service_orders(order_id) ON DELETE CASCADE,
            run_id text,
            idempotency_key text NOT NULL UNIQUE,
            status text NOT NULL CHECK (
                status IN ('intent', 'pending', 'confirmed', 'rejected', 'unknown')
            ),
            site text,
            appointment_date text,
            appointment_hour text,
            evidence_path text,
            details_json jsonb,
            submitted_at timestamptz,
            resolved_at timestamptz,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reservation_attempts_order_created
        ON reservation_attempts(order_id, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_reservation_attempts_active_order
        ON reservation_attempts(order_id)
        WHERE status IN ('intent', 'pending', 'unknown')
        """
    )


def _create_worker_commands_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_commands (
            command_id text PRIMARY KEY,
            command text NOT NULL CHECK (command IN ('pause', 'resume', 'restart')),
            status text NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'processing', 'applied', 'failed')
            ),
            requested_by text,
            worker_owner_token text,
            requested_at timestamptz NOT NULL,
            claimed_at timestamptz,
            processed_at timestamptz,
            error_message text,
            CONSTRAINT ck_worker_commands_processing CHECK (
                status <> 'processing' OR claimed_at IS NOT NULL
            ),
            CONSTRAINT ck_worker_commands_done CHECK (
                status NOT IN ('applied', 'failed') OR processed_at IS NOT NULL
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_worker_commands_pending
        ON worker_commands(requested_at ASC, command_id ASC)
        WHERE status = 'pending'
        """
    )


def _create_remote_control_audit_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS remote_control_audit (
            audit_id text PRIMARY KEY,
            actor text NOT NULL,
            action text NOT NULL,
            target_type text,
            target_id text,
            status text NOT NULL CHECK (
                status IN ('accepted', 'applied', 'failed', 'cancelled',
                           'denied', 'rate_limited', 'started')
            ),
            operation_id text,
            detail text,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_remote_control_audit_created
        ON remote_control_audit(created_at DESC, audit_id DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_remote_control_audit_target
        ON remote_control_audit(target_type, target_id, created_at DESC)
        """
    )


def _create_finance_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_categories (
            category_code text PRIMARY KEY,
            display_name text NOT NULL,
            cost_behavior text NOT NULL CHECK (cost_behavior IN ('variable', 'fixed', 'mixed')),
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO finance_categories (category_code, display_name, cost_behavior)
        VALUES
            ('captcha', 'CAPTCHA', 'variable'),
            ('marketing', 'Marketing y publicidad', 'variable'),
            ('payment_fee', 'Comisiones de cobro', 'variable'),
            ('government_fee', 'Tasas oficiales por cuenta del cliente', 'variable'),
            ('refund', 'Devoluciones', 'variable'),
            ('internet', 'Internet', 'fixed'),
            ('electricity', 'Electricidad', 'mixed'),
            ('hosting', 'Hosting e infraestructura', 'fixed'),
            ('backup', 'Backups', 'fixed'),
            ('equipment', 'Equipos', 'fixed'),
            ('human_time', 'Tiempo humano', 'mixed'),
            ('tax', 'Impuestos', 'variable'),
            ('other', 'Otros', 'mixed')
        ON CONFLICT (category_code) DO NOTHING
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_entries (
            entry_id text PRIMARY KEY,
            occurred_on date NOT NULL,
            entry_kind text NOT NULL CHECK (
                entry_kind IN ('expense', 'prepaid_topup', 'prepaid_consumption', 'refund')
            ),
            category_code text NOT NULL REFERENCES finance_categories(category_code),
            vendor text,
            description text NOT NULL,
            amount_original numeric(12, 4) NOT NULL CHECK (amount_original > 0),
            currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
            exchange_rate_pen numeric(12, 6) CHECK (
                exchange_rate_pen IS NULL OR exchange_rate_pen > 0
            ),
            amount_pen numeric(12, 2) CHECK (amount_pen IS NULL OR amount_pen > 0),
            quantity numeric(12, 3) CHECK (quantity IS NULL OR quantity > 0),
            unit text,
            channel text,
            campaign text,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            evidence_reference text,
            notes text,
            data_quality text NOT NULL DEFAULT 'actual' CHECK (
                data_quality IN ('actual', 'estimated', 'pending')
            ),
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'voided')),
            voided_at timestamptz,
            void_reason text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_finance_entries_conversion CHECK (
                (currency = 'PEN' AND exchange_rate_pen = 1 AND amount_pen IS NOT NULL)
                OR currency <> 'PEN'
            ),
            CONSTRAINT ck_finance_entries_void CHECK (
                (status = 'active' AND voided_at IS NULL AND void_reason IS NULL)
                OR (status = 'voided' AND voided_at IS NOT NULL AND void_reason IS NOT NULL)
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_finance_entries_occurred
        ON finance_entries(occurred_on DESC, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_finance_entries_active_month
        ON finance_entries(occurred_on, entry_kind, category_code)
        WHERE status = 'active'
        """
    )


def _create_finance_month_closure_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_month_closures (
            month_start date PRIMARY KEY CHECK (date_trunc('month', month_start) = month_start),
            opening_prepaid_balance numeric(12, 2) CHECK (
                opening_prepaid_balance IS NULL OR opening_prepaid_balance >= 0
            ),
            closing_prepaid_balance numeric(12, 2) CHECK (
                closing_prepaid_balance IS NULL OR closing_prepaid_balance >= 0
            ),
            status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'reconciled')),
            reconciled_at timestamptz,
            reconciled_by text,
            notes text,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_finance_month_closure_reconciliation CHECK (
                (
                    status = 'draft'
                    AND reconciled_at IS NULL
                    AND reconciled_by IS NULL
                )
                OR (
                    status = 'reconciled'
                    AND opening_prepaid_balance IS NOT NULL
                    AND closing_prepaid_balance IS NOT NULL
                    AND reconciled_at IS NOT NULL
                    AND length(btrim(reconciled_by)) > 0
                )
            )
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_amount_reconciliations (
            payment_id text PRIMARY KEY REFERENCES payments(payment_id) ON DELETE CASCADE,
            resolution_type text NOT NULL CHECK (
                resolution_type IN ('discount', 'waiver', 'correction')
            ),
            reason text NOT NULL,
            reconciled_by text NOT NULL,
            reconciled_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_payment_amount_reconciliation_reason CHECK (
                length(btrim(reason)) >= 3 AND length(btrim(reconciled_by)) > 0
            )
        )
        """
    )


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


def _promote_stable_runtime_schema(connection: Connection) -> None:
    connection.execute(
        """
        UPDATE opportunity_runtime_control
        SET burst_mode = 'enabled'
        WHERE burst_mode = 'inherit'
        """
    )
    connection.execute(
        """
        UPDATE opportunity_runtime_control
        SET obs007_mode = 'enabled'
        WHERE obs007_mode = 'inherit'
        """
    )
    connection.execute(
        """
        ALTER TABLE opportunity_runtime_control
        ALTER COLUMN burst_mode SET DEFAULT 'enabled',
        ALTER COLUMN obs007_mode SET DEFAULT 'enabled',
        DROP CONSTRAINT IF EXISTS opportunity_runtime_control_burst_mode_check,
        DROP CONSTRAINT IF EXISTS opportunity_runtime_control_obs007_mode_check,
        DROP CONSTRAINT IF EXISTS ck_opportunity_runtime_control_burst_mode,
        DROP CONSTRAINT IF EXISTS ck_opportunity_runtime_control_obs007_mode,
        ADD CONSTRAINT ck_opportunity_runtime_control_burst_mode CHECK (
            burst_mode IN ('enabled', 'disabled', 'draining')
        ),
        ADD CONSTRAINT ck_opportunity_runtime_control_obs007_mode CHECK (
            obs007_mode IN ('enabled', 'disabled')
        )
        """
    )
    connection.execute(
        """
        UPDATE appointment_reminder_control
        SET mode = 'live'
        WHERE mode = 'canary'
        """
    )
    connection.execute(
        """
        ALTER TABLE appointment_reminder_control
        DROP CONSTRAINT IF EXISTS appointment_reminder_control_mode_check,
        DROP CONSTRAINT IF EXISTS ck_appointment_reminder_control_mode,
        ADD CONSTRAINT ck_appointment_reminder_control_mode CHECK (
            mode IN ('disabled', 'dry_run', 'live')
        ),
        DROP COLUMN IF EXISTS canary_order_ids
        """
    )


def _create_whatsapp_message_template_schema(connection: Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS whatsapp_message_templates (
            template_key text PRIMARY KEY CHECK (
                char_length(template_key) BETWEEN 1 AND 80
            ),
            message_template text NOT NULL CHECK (
                char_length(message_template) BETWEEN 1 AND {MAX_TEMPLATE_LENGTH}
            ),
            revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
            enabled boolean NOT NULL DEFAULT true,
            updated_at timestamptz NOT NULL,
            updated_by text NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS whatsapp_message_template_versions (
            template_key text NOT NULL REFERENCES whatsapp_message_templates(template_key),
            revision integer NOT NULL CHECK (revision >= 1),
            message_template text NOT NULL CHECK (
                char_length(message_template) BETWEEN 1 AND {MAX_TEMPLATE_LENGTH}
            ),
            created_at timestamptz NOT NULL,
            created_by text NOT NULL,
            PRIMARY KEY (template_key, revision)
        )
        """
    )
    now = datetime.now(UTC)
    for definition in WHATSAPP_TEMPLATE_DEFINITIONS.values():
        connection.execute(
            """
            INSERT INTO whatsapp_message_templates (
                template_key, message_template, revision, enabled, updated_at, updated_by
            ) VALUES (%s, %s, 1, true, %s, 'schema-migration')
            ON CONFLICT (template_key) DO NOTHING
            """,
            (definition.key, definition.current_default_template, now),
        )
        connection.execute(
            """
            INSERT INTO whatsapp_message_template_versions (
                template_key, revision, message_template, created_at, created_by
            ) VALUES (%s, 1, %s, %s, 'schema-migration')
            ON CONFLICT (template_key, revision) DO NOTHING
            """,
            (definition.key, definition.current_default_template, now),
        )


def _create_whatsapp_automation_template_trace_schema(connection: Connection) -> None:
    connection.execute(
        """
        ALTER TABLE whatsapp_automation_jobs
        ADD COLUMN IF NOT EXISTS template_key text,
        ADD COLUMN IF NOT EXISTS template_revision integer
        """
    )
    constraint = connection.execute(
        """
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_whatsapp_automation_template_trace'
          AND conrelid = 'whatsapp_automation_jobs'::regclass
        """
    ).fetchone()
    if constraint is None:
        connection.execute(
            """
            ALTER TABLE whatsapp_automation_jobs
            ADD CONSTRAINT ck_whatsapp_automation_template_trace CHECK (
                (template_key IS NULL AND template_revision IS NULL)
                OR (
                    template_key IS NOT NULL
                    AND char_length(template_key) BETWEEN 1 AND 80
                    AND template_revision IS NOT NULL
                    AND template_revision > 0
                )
            )
            """
        )


def _create_whatsapp_message_template_trace_schema(connection: Connection) -> None:
    connection.execute(
        """
        ALTER TABLE whatsapp_messages
        ADD COLUMN IF NOT EXISTS confirmation_template_key text,
        ADD COLUMN IF NOT EXISTS confirmation_template_revision integer,
        ADD COLUMN IF NOT EXISTS payment_template_key text,
        ADD COLUMN IF NOT EXISTS payment_template_revision integer
        """
    )
    for constraint_name, key_column, revision_column in (
        (
            "ck_whatsapp_messages_confirmation_template_trace",
            "confirmation_template_key",
            "confirmation_template_revision",
        ),
        (
            "ck_whatsapp_messages_payment_template_trace",
            "payment_template_key",
            "payment_template_revision",
        ),
    ):
        constraint = connection.execute(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conname = %s
              AND conrelid = 'whatsapp_messages'::regclass
            """,
            (constraint_name,),
        ).fetchone()
        if constraint is None:
            connection.execute(
                f"""
                ALTER TABLE whatsapp_messages
                ADD CONSTRAINT {constraint_name} CHECK (
                    ({key_column} IS NULL AND {revision_column} IS NULL)
                    OR (
                        {key_column} IS NOT NULL
                        AND char_length({key_column}) BETWEEN 1 AND 80
                        AND {revision_column} IS NOT NULL
                        AND {revision_column} > 0
                    )
                )
                """
            )


def _create_whatsapp_followup_template_trace_schema(connection: Connection) -> None:
    connection.execute(
        """
        ALTER TABLE whatsapp_followup_messages
        ADD COLUMN IF NOT EXISTS message_text text,
        ADD COLUMN IF NOT EXISTS template_key text,
        ADD COLUMN IF NOT EXISTS template_revision integer
        """
    )
    constraint = connection.execute(
        """
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_whatsapp_followup_messages_template_trace'
          AND conrelid = 'whatsapp_followup_messages'::regclass
        """
    ).fetchone()
    if constraint is None:
        connection.execute(
            """
            ALTER TABLE whatsapp_followup_messages
            ADD CONSTRAINT ck_whatsapp_followup_messages_template_trace CHECK (
                (
                    message_text IS NULL
                    AND template_key IS NULL
                    AND template_revision IS NULL
                )
                OR (
                    message_text IS NOT NULL
                    AND char_length(message_text) BETWEEN 1 AND 4096
                    AND template_key IS NOT NULL
                    AND char_length(template_key) BETWEEN 1 AND 80
                    AND template_revision IS NOT NULL
                    AND template_revision > 0
                )
            )
            """
        )


def _unify_appointment_reminder_template_schema(connection: Connection) -> None:
    control = connection.execute(
        """
        SELECT message_template, revision, updated_at, updated_by
        FROM appointment_reminder_control
        WHERE id = 1
        """
    ).fetchone()
    template = connection.execute(
        """
        SELECT revision, updated_by
        FROM whatsapp_message_templates
        WHERE template_key = 'appointment_reminder'
        """
    ).fetchone()
    if control is None or template is None:
        raise RuntimeError("Appointment reminder template state is incomplete.")
    if int(template["revision"]) != 1 or str(template["updated_by"]) != "schema-migration":
        return
    legacy_versions = connection.execute(
        """
        SELECT revision, message_template, created_at, created_by
        FROM appointment_reminder_template_versions
        WHERE revision > 1
        ORDER BY revision
        """
    ).fetchall()
    for version in legacy_versions:
        connection.execute(
            """
            INSERT INTO whatsapp_message_template_versions (
                template_key, revision, message_template, created_at, created_by
            ) VALUES ('appointment_reminder', %s, %s, %s, %s)
            ON CONFLICT (template_key, revision) DO NOTHING
            """,
            (
                version["revision"],
                version["message_template"],
                version["created_at"],
                version["created_by"],
            ),
        )
    target_revision = max(int(control["revision"]), 2)
    connection.execute(
        """
        INSERT INTO whatsapp_message_template_versions (
            template_key, revision, message_template, created_at, created_by
        ) VALUES ('appointment_reminder', %s, %s, %s, %s)
        ON CONFLICT (template_key, revision) DO NOTHING
        """,
        (
            target_revision,
            control["message_template"],
            control["updated_at"],
            control["updated_by"],
        ),
    )
    connection.execute(
        """
        UPDATE whatsapp_message_templates
        SET message_template = %s,
            revision = %s,
            updated_at = %s,
            updated_by = %s
        WHERE template_key = 'appointment_reminder'
          AND revision = 1
          AND updated_by = 'schema-migration'
        """,
        (
            control["message_template"],
            target_revision,
            control["updated_at"],
            control["updated_by"],
        ),
    )


def _retire_appointment_reminder_legacy_schema(connection: Connection) -> None:
    legacy_table = connection.execute(
        "SELECT to_regclass('appointment_reminder_template_versions') AS table_name"
    ).fetchone()
    if legacy_table is None or legacy_table["table_name"] is None:
        raise RuntimeError("Legacy appointment reminder template history is missing.")

    legacy_versions = connection.execute(
        """
        SELECT revision, message_template, created_at, created_by
        FROM appointment_reminder_template_versions
        ORDER BY revision
        """
    ).fetchall()
    if not legacy_versions:
        raise RuntimeError("Legacy appointment reminder template history is empty.")

    for version in legacy_versions:
        revision = int(version["revision"])
        current = connection.execute(
            """
            SELECT message_template
            FROM whatsapp_message_template_versions
            WHERE template_key = 'appointment_reminder' AND revision = %s
            """,
            (revision,),
        ).fetchone()
        if current is not None and str(current["message_template"]) != str(
            version["message_template"]
        ):
            references = connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM whatsapp_automation_jobs
                     WHERE template_key = 'appointment_reminder'
                       AND template_revision = %s)
                  + (SELECT count(*) FROM whatsapp_followup_messages
                     WHERE template_key = 'appointment_reminder'
                       AND template_revision = %s)
                  + (SELECT count(*) FROM whatsapp_messages
                     WHERE confirmation_template_key = 'appointment_reminder'
                       AND confirmation_template_revision = %s)
                  + (SELECT count(*) FROM whatsapp_messages
                     WHERE payment_template_key = 'appointment_reminder'
                       AND payment_template_revision = %s) AS count
                """,
                (revision, revision, revision, revision),
            ).fetchone()
            if references is not None and int(references["count"]) > 0:
                raise RuntimeError(
                    "Cannot replace differing appointment reminder template "
                    f"revision {revision}; persisted work references it."
                )
        connection.execute(
            """
            INSERT INTO whatsapp_message_template_versions (
                template_key, revision, message_template, created_at, created_by
            ) VALUES ('appointment_reminder', %s, %s, %s, %s)
            ON CONFLICT (template_key, revision) DO UPDATE
            SET message_template = EXCLUDED.message_template,
                created_at = EXCLUDED.created_at,
                created_by = EXCLUDED.created_by
            """,
            (
                revision,
                version["message_template"],
                version["created_at"],
                version["created_by"],
            ),
        )

    mismatch = connection.execute(
        """
        SELECT count(*) AS count
        FROM appointment_reminder_template_versions legacy
        LEFT JOIN whatsapp_message_template_versions unified
          ON unified.template_key = 'appointment_reminder'
         AND unified.revision = legacy.revision
        WHERE unified.revision IS NULL
           OR unified.message_template IS DISTINCT FROM legacy.message_template
           OR unified.created_at IS DISTINCT FROM legacy.created_at
           OR unified.created_by IS DISTINCT FROM legacy.created_by
        """
    ).fetchone()
    if mismatch is None or int(mismatch["count"]) != 0:
        raise RuntimeError("Appointment reminder template history was not preserved.")

    missing_frozen_text = connection.execute(
        """
        SELECT count(*) AS count
        FROM whatsapp_automation_jobs
        WHERE job_kind = 'appointment_reminder'
          AND NULLIF(BTRIM(message_text), '') IS NULL
        """
    ).fetchone()
    if missing_frozen_text is None or int(missing_frozen_text["count"]) != 0:
        raise RuntimeError("An appointment reminder job has no frozen message text.")

    connection.execute(
        "ALTER TABLE appointment_reminder_control DROP COLUMN message_template"
    )
    connection.execute("DROP TABLE appointment_reminder_template_versions")


def _freeze_historical_whatsapp_followup_text(connection: Connection) -> None:
    rows = connection.execute(
        """
        SELECT message_id, steps, template_key, template_revision
        FROM whatsapp_followup_messages
        WHERE NULLIF(BTRIM(message_text), '') IS NULL
        ORDER BY message_id
        """
    ).fetchall()
    traced = [
        row
        for row in rows
        if row["template_key"] is not None or row["template_revision"] is not None
    ]
    if traced:
        raise RuntimeError("A traced post-payment package has no frozen message text.")

    connection.execute(
        """
        ALTER TABLE whatsapp_followup_messages
        DROP CONSTRAINT ck_whatsapp_followup_messages_template_trace
        """
    )
    for row in rows:
        steps_value = row["steps"]
        if isinstance(steps_value, str):
            steps_value = json.loads(steps_value)
        if not isinstance(steps_value, list):
            raise RuntimeError("A historical post-payment package has invalid steps.")
        steps = [item for item in steps_value if isinstance(item, dict)]
        full_text = "\n\n".join(str(step.get("text") or "").strip() for step in steps)
        detail_lines: list[str] = []
        for label in ("Reserva", "Sede"):
            prefix = f"{label}:"
            value = next(
                (
                    line[len(prefix) :].strip()
                    for line in full_text.splitlines()
                    if line.startswith(prefix) and line[len(prefix) :].strip()
                ),
                "",
            )
            if value:
                detail_lines.append(f"{label}: {value}")
        details = "\n" + "\n".join(detail_lines) if detail_lines else ""
        message_text = (
            "✅ *¡Pago confirmado!*\n"
            "Cita reservada. Llegue 30 min antes y vaya con el vehículo ya polarizado."
            f"{details}\n\n"
            "📄 Lleve los PDFs adjuntos impresos, llenados y firmados. Revise requisitos "
            "y copias.\n\n"
            "🔍 El peritaje dura aprox. 5 min. Después de pasarlo, en 2 días consulte "
            "su autorización virtual en la misma web de reserva.\n\n"
            "Gracias por confiar en nosotros. Si puede dejarnos un comentario en TikTok "
            "nos ayuda muchísimo: @citaspolarizadasperu"
        )
        if len(message_text) > 4096:
            raise RuntimeError("A historical post-payment package exceeds 4096 characters.")
        connection.execute(
            """
            UPDATE whatsapp_followup_messages
            SET message_text = %s, updated_at = CURRENT_TIMESTAMP
            WHERE message_id = %s
            """,
            (message_text, row["message_id"]),
        )

    connection.execute(
        "ALTER TABLE whatsapp_followup_messages ALTER COLUMN message_text SET NOT NULL"
    )
    connection.execute(
        """
        ALTER TABLE whatsapp_followup_messages
        ADD CONSTRAINT ck_whatsapp_followup_messages_template_trace CHECK (
            char_length(message_text) BETWEEN 1 AND 4096
            AND (
                (template_key IS NULL AND template_revision IS NULL)
                OR (
                    template_key IS NOT NULL
                    AND char_length(template_key) BETWEEN 1 AND 80
                    AND template_revision IS NOT NULL
                    AND template_revision > 0
                )
            )
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


def _create_captcha_shadow_outbox_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS captcha_shadow_outbox (
            event_key text PRIMARY KEY,
            event_id text NOT NULL,
            sequence smallint NOT NULL CHECK (sequence BETWEEN 1 AND 3),
            endpoint text NOT NULL CHECK (
                endpoint IN ('/v1/predict', '/v1/results/external')
            ),
            payload jsonb NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'processed')
            ),
            attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at timestamptz,
            UNIQUE (event_id, sequence)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_captcha_shadow_outbox_pending
        ON captcha_shadow_outbox(next_attempt_at, created_at)
        WHERE status = 'pending'
        """
    )


def _create_telegram_alert_outbox_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_alert_outbox (
            dedupe_key text PRIMARY KEY,
            payload jsonb NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'sent', 'failed')
            ),
            attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sent_at timestamptz
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_telegram_alert_outbox_pending
        ON telegram_alert_outbox(next_attempt_at, created_at)
        WHERE status = 'pending'
        """
    )


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
        _validate_current_schema(connection)
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
        _create_whatsapp_messages_schema(connection)
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
        _create_whatsapp_followup_messages_schema(connection)
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
        _create_whatsapp_automation_jobs_schema(connection)
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
    if current_version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is unsupported; "
            f"this installation requires version {SCHEMA_VERSION}."
        )
    _validate_current_schema(connection)
