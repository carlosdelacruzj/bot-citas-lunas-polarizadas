from __future__ import annotations

from psycopg import Connection


def v24_to_v25(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN closure_reason text CHECK (
                closure_reason IS NULL OR closure_reason IN (
                    'completed_by_us',
                    'family_no_charge',
                    'client_withdrew',
                    'external_slot',
                    'duplicate',
                    'not_serviceable'
                )
            )
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN closure_note text
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN closed_at timestamptz
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (25,),
    )
