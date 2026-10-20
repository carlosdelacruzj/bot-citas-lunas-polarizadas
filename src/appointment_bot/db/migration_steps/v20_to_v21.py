from __future__ import annotations

from psycopg import Connection


def v20_to_v21(connection: Connection) -> None:
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
