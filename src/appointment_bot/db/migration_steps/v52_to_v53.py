from __future__ import annotations

from psycopg import Connection


def v52_to_v53(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN acquisition_source text
            """
    )
    connection.execute(
        """
            UPDATE service_orders so
            SET acquisition_source = NULLIF(BTRIM(wc.contact_source), '')
            FROM applicant_contacts ac
            JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            WHERE ac.applicant_id = so.applicant_id
              AND ac.is_primary = true
              AND so.acquisition_source IS NULL
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (53,),
    )
