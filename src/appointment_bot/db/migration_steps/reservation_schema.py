from __future__ import annotations

from psycopg import Connection


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
