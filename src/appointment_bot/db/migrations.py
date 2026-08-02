from __future__ import annotations

from datetime import UTC, datetime

from psycopg import Connection

SCHEMA_VERSION = 42
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
            display_name text,
            contact_source text NOT NULL DEFAULT 'whatsapp',
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        )
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
            reservation_price numeric(12, 2) NOT NULL DEFAULT 50.00 CHECK (
                reservation_price > 0
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
                    'not_serviceable'
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
            preflight_details jsonb
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
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid')),
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
    _create_whatsapp_messages_schema(connection)
    _create_whatsapp_followup_messages_schema(connection)
    _create_whatsapp_automation_jobs_schema(connection)
    _create_captcha_shadow_outbox_schema(connection)
    _create_hosted_registration_schema(connection)


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
        "worker_state",
        "worker_commands",
        "remote_control_audit",
        "finance_categories",
        "finance_entries",
        "whatsapp_messages",
        "whatsapp_followup_messages",
        "whatsapp_automation_jobs",
        "captcha_shadow_outbox",
        "hosted_registration_contacts",
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
        ("portal_accounts", "applicant_id"),
        ("portal_accounts", "password"),
        ("portal_accounts", "document_type"),
        ("service_orders", "status"),
        ("service_orders", "reservation_price"),
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
        ("reservation_attempts", "idempotency_key"),
        ("reservation_attempts", "status"),
        ("reservations", "run_id"),
        ("reservations", "status"),
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
        ("whatsapp_messages", "message_id"),
        ("whatsapp_messages", "recipient_phone"),
        ("whatsapp_messages", "attachment_path"),
        ("whatsapp_messages", "payment_attachment_path"),
        ("whatsapp_messages", "status"),
        ("whatsapp_messages", "test_mode"),
        ("whatsapp_messages", "sent_at"),
        ("whatsapp_followup_messages", "message_id"),
        ("whatsapp_followup_messages", "recipient_phone"),
        ("whatsapp_followup_messages", "steps"),
        ("whatsapp_followup_messages", "status"),
        ("whatsapp_followup_messages", "test_mode"),
        ("whatsapp_followup_messages", "sent_at"),
        ("whatsapp_automation_jobs", "job_key"),
        ("whatsapp_automation_jobs", "order_id"),
        ("whatsapp_automation_jobs", "job_kind"),
        ("whatsapp_automation_jobs", "status"),
        ("whatsapp_automation_jobs", "attempt_count"),
        ("whatsapp_automation_jobs", "lease_expires_at"),
        ("whatsapp_automation_jobs", "next_attempt_at"),
        ("whatsapp_automation_jobs", "preflight_error"),
        ("whatsapp_automation_jobs", "preflight_alerted_at"),
        ("whatsapp_automation_jobs", "report_date"),
        ("whatsapp_automation_jobs", "recipient_phone"),
        ("whatsapp_automation_jobs", "message_text"),
        ("whatsapp_automation_jobs", "publication_text"),
        ("whatsapp_automation_jobs", "attachment_paths"),
        ("captcha_shadow_outbox", "event_key"),
        ("captcha_shadow_outbox", "event_id"),
        ("captcha_shadow_outbox", "sequence"),
        ("captcha_shadow_outbox", "status"),
        ("captcha_shadow_outbox", "next_attempt_at"),
        ("hosted_registration_contacts", "contact_ref"),
        ("hosted_registration_contacts", "whatsapp_phone"),
        ("hosted_registration_contacts", "invitation_id"),
        ("hosted_registration_contacts", "request_id"),
        ("hosted_registration_contacts", "order_id"),
        ("hosted_registration_contacts", "state"),
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
        "ck_whatsapp_followup_messages_sent",
        "ck_whatsapp_automation_job_status",
        "ck_whatsapp_automation_job_attempt",
        "ck_whatsapp_automation_job_kind",
        "ck_whatsapp_automation_job_target",
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
    if "uq_whatsapp_automation_jobs_running" not in indexes:
        missing.append("uq_whatsapp_automation_jobs_running")
    if "idx_captcha_shadow_outbox_pending" not in indexes:
        missing.append("idx_captcha_shadow_outbox_pending")
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


def _create_whatsapp_messages_schema(connection: Connection) -> None:
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


def _create_whatsapp_followup_messages_schema(connection: Connection) -> None:
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


def _create_whatsapp_automation_jobs_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_automation_jobs (
            job_key text PRIMARY KEY,
            order_id text REFERENCES service_orders(order_id) ON DELETE CASCADE,
            job_kind text NOT NULL,
            report_date date,
            recipient_phone text,
            message_text text,
            publication_text text,
            attachment_paths jsonb,
            status text NOT NULL DEFAULT 'queued',
            message_id text,
            attempt_count smallint NOT NULL DEFAULT 0 CHECK (
                attempt_count BETWEEN 0 AND 1
            ),
            lease_owner text,
            lease_expires_at timestamptz,
            error_message text,
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
                    'daily_slot_summary'
                )
            ),
            CONSTRAINT ck_whatsapp_automation_job_target CHECK (
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
        _create_hosted_registration_schema(connection)
        connection.execute(
            "UPDATE schema_version SET version = %s WHERE id = 1",
            (38,),
        )
        current_version = 38
    if current_version == 38:
        connection.execute(
            """
            ALTER TABLE hosted_registration_contacts
            ALTER COLUMN display_name DROP NOT NULL
            """
        )
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
    if current_version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is unsupported; "
            f"this installation requires version {SCHEMA_VERSION}."
        )
    _validate_current_schema(connection)


def _create_hosted_registration_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS hosted_registration_contacts (
            contact_ref text PRIMARY KEY,
            whatsapp_phone text NOT NULL,
            display_name text,
            invitation_id text UNIQUE,
            request_id text UNIQUE,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            state text NOT NULL DEFAULT 'local_pending' CHECK (
                state IN (
                    'local_pending', 'issued', 'opened', 'submitted', 'leased',
                    'accepted', 'credentials_invalid', 'rejected', 'revoked',
                    'expired', 'cancelled', 'retry_wait', 'awaiting_restrictions',
                    'configuration_error'
                )
            ),
            availability_mode text CHECK (
                availability_mode IS NULL
                OR availability_mode IN ('any_date', 'date_restrictions')
            ),
            last_error_category text,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hosted_registration_contacts_state
        ON hosted_registration_contacts(state, updated_at DESC)
        """
    )
