from __future__ import annotations

from psycopg import Connection


def v71_to_v72(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE opportunity_bursts
            DROP CONSTRAINT IF EXISTS opportunity_bursts_configured_max_sessions_check,
            DROP CONSTRAINT IF EXISTS opportunity_bursts_max_active_sessions_check,
            DROP CONSTRAINT IF EXISTS ck_opportunity_bursts_configured_max_sessions,
            DROP CONSTRAINT IF EXISTS ck_opportunity_bursts_max_active_sessions
            """
    )
    connection.execute(
        """
            ALTER TABLE opportunity_bursts
            ADD CONSTRAINT ck_opportunity_bursts_configured_max_sessions CHECK (
                configured_max_sessions BETWEEN 1 AND 3
            ),
            ADD CONSTRAINT ck_opportunity_bursts_max_active_sessions CHECK (
                max_active_sessions BETWEEN 0 AND 3
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (72,),
    )
