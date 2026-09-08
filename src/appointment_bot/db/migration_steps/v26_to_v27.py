from __future__ import annotations

from psycopg import Connection


def v26_to_v27(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN maximum_date date
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD CONSTRAINT ck_service_orders_reservation_date_range CHECK (
                maximum_date IS NULL OR minimum_date IS NULL OR maximum_date >= minimum_date
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (27,),
    )
