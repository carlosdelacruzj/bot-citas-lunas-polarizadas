from __future__ import annotations

from datetime import UTC, datetime

from psycopg import Connection


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
