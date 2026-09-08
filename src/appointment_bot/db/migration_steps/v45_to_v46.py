from __future__ import annotations

from psycopg import Connection


def v45_to_v46(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            DROP CONSTRAINT service_orders_closure_reason_check,
            ADD CONSTRAINT service_orders_closure_reason_check CHECK (
                closure_reason IS NULL OR closure_reason IN (
                    'completed_by_us',
                    'family_no_charge',
                    'client_withdrew',
                    'external_slot',
                    'duplicate',
                    'not_serviceable',
                    'uncollectible'
                )
            )
            """
    )
    connection.execute(
        """
            ALTER TABLE payments
            DROP CONSTRAINT payments_status_check,
            ADD CONSTRAINT payments_status_check CHECK (
                status IN ('pending', 'paid', 'written_off')
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (46,),
    )
