from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.reservation_schema import (
    _create_reservation_attempts_schema,
)


def v15_to_v16(connection: Connection) -> None:
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
