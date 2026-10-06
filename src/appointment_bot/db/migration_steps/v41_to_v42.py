from __future__ import annotations

from psycopg import Connection


def v41_to_v42(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN reservation_price numeric(12, 2) NOT NULL DEFAULT 40.00
                CHECK (reservation_price > 0)
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            ALTER COLUMN reservation_price SET DEFAULT 50.00
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (42,),
    )
