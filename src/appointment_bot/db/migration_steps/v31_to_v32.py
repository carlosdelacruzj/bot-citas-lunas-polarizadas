from __future__ import annotations

from psycopg import Connection


def v31_to_v32(connection: Connection) -> None:
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
