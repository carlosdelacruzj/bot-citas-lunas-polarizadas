from __future__ import annotations

from psycopg import Connection


def v58_to_v59(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN service_type text NOT NULL DEFAULT 'standard' CHECK (
                service_type IN ('standard', 'selected_date', 'custom')
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (59,),
    )
