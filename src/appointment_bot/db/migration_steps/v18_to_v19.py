from __future__ import annotations

from psycopg import Connection


def v18_to_v19(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN minimum_date date
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (19,),
    )
