from __future__ import annotations

from psycopg import Connection


def v28_to_v29(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE whatsapp_messages
            ADD COLUMN IF NOT EXISTS payment_attachment_path text
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (29,),
    )
