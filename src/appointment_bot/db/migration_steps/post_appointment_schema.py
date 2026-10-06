from __future__ import annotations

from psycopg import Connection


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
