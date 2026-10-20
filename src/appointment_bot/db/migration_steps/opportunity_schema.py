from __future__ import annotations

from psycopg import Connection


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
            configured_max_sessions smallint NOT NULL,
            CONSTRAINT ck_opportunity_bursts_configured_max_sessions CHECK (
                configured_max_sessions BETWEEN 1 AND 3
            ),
            configured_max_clients integer NOT NULL CHECK (configured_max_clients >= 0),
            max_active_sessions smallint NOT NULL DEFAULT 1,
            CONSTRAINT ck_opportunity_bursts_max_active_sessions CHECK (
                max_active_sessions BETWEEN 0 AND 3
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
