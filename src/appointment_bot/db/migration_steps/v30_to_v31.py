from __future__ import annotations

from psycopg import Connection


def v30_to_v31(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE portal_accounts
            ADD COLUMN document_type text NOT NULL DEFAULT 'dni' CHECK (
                document_type IN ('dni', 'foreign_resident_card')
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (31,),
    )
