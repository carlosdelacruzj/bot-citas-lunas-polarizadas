from __future__ import annotations

from psycopg import Connection


def v59_to_v60(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            DROP CONSTRAINT IF EXISTS service_orders_service_type_check
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            DROP CONSTRAINT IF EXISTS ck_service_orders_service_type
            """
    )
    connection.execute(
        """
            UPDATE service_orders
            SET service_type = 'selected_weekday',
                allowed_weekdays = ARRAY[
                    EXTRACT(ISODOW FROM minimum_date)::smallint
                ],
                minimum_date = NULL,
                maximum_date = NULL
            WHERE service_type = 'selected_date'
              AND minimum_date IS NOT NULL
              AND minimum_date = maximum_date
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD CONSTRAINT ck_service_orders_service_type CHECK (
                service_type IN ('standard', 'selected_weekday', 'custom')
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (60,),
    )
