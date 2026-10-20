from __future__ import annotations

from psycopg import Connection


def v34_to_v35(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN excluded_date_ranges jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
                jsonb_typeof(excluded_date_ranges) = 'array'
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (35,),
    )
