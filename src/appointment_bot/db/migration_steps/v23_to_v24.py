from __future__ import annotations

from psycopg import Connection


def v23_to_v24(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN parent_order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN program_expediente text
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN program_plate text
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (24,),
    )
