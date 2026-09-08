from __future__ import annotations

from psycopg import Connection


def v16_to_v17(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE order_state
            ADD COLUMN credential_failures integer NOT NULL DEFAULT 0
                CHECK (credential_failures >= 0)
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (17,),
    )
