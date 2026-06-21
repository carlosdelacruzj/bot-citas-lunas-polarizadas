from __future__ import annotations

from datetime import UTC, datetime

from psycopg import Connection

SCHEMA_VERSION = 14
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
            phone text NOT NULL UNIQUE,
            display_name text,
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
            minimum_hour integer CHECK (
                minimum_hour IS NULL OR (minimum_hour >= 0 AND minimum_hour <= 23)
            ),
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
            next_allowed_at timestamptz,
            last_run_at timestamptz,
            last_success_at timestamptz,
            programmed_at timestamptz
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
        "run_screenshots",
        "reservations",
        "payments",
        "worker_state",
    }
    tables = {
        row["table_name"]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema()"
        )
    }
    required_columns = {
        ("schema_version", "version"),
        ("portal_accounts", "applicant_id"),
        ("portal_accounts", "password"),
        ("service_orders", "status"),
        ("service_orders", "minimum_hour"),
        ("service_orders", "lease_owner"),
        ("service_orders", "lease_expires_at"),
        ("runs", "reservation_attempted"),
        ("runs", "reservation_confirmed"),
        ("reservations", "run_id"),
        ("reservations", "status"),
        ("payments", "reservation_id"),
        ("payments", "status"),
        ("worker_state", "current_order_id"),
        ("worker_state", "owner_token"),
        ("worker_state", "lease_expires_at"),
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
    }
    constraint_rows = connection.execute(
        "SELECT conname, convalidated FROM pg_constraint "
        "WHERE connamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())"
    ).fetchall()
    constraints = {
        row["conname"]
        for row in constraint_rows
    }
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
    if missing:
        raise RuntimeError("Database schema v14 is incomplete: " + ", ".join(missing))


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
    if current_version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is unsupported; "
            f"this installation requires version {SCHEMA_VERSION}."
        )
    _validate_current_schema(connection)
