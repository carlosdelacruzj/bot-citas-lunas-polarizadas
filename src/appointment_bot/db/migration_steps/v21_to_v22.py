from __future__ import annotations

from psycopg import Connection


def v21_to_v22(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE whatsapp_contacts
            ADD COLUMN contact_source text NOT NULL DEFAULT 'whatsapp'
            """
    )
    connection.execute("ALTER TABLE whatsapp_contacts ALTER COLUMN phone DROP NOT NULL")
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (22,),
    )
