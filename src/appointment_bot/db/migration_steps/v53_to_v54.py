from __future__ import annotations

from psycopg import Connection


def v53_to_v54(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN acquisition_source_origin text CHECK (
                acquisition_source_origin IS NULL OR acquisition_source_origin IN (
                    'order_creation', 'historical_backfill'
                )
            )
            """
    )
    connection.execute(
        """
            UPDATE service_orders
            SET acquisition_source_origin = 'historical_backfill'
            WHERE acquisition_source IS NOT NULL
              AND acquisition_source_origin IS NULL
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (54,),
    )
