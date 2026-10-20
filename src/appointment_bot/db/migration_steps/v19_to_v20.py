from __future__ import annotations

from psycopg import Connection


def v19_to_v20(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN allowed_weekdays smallint[] CHECK (
                allowed_weekdays IS NULL
                OR allowed_weekdays <@ ARRAY[1,2,3,4,5,6,7]::smallint[]
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (20,),
    )
