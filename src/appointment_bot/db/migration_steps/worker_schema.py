from __future__ import annotations

from psycopg import Connection


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
