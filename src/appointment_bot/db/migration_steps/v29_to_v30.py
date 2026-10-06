from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.whatsapp_legacy import (
    create_legacy_whatsapp_followup_messages_schema,
)


def v29_to_v30(connection: Connection) -> None:
    create_legacy_whatsapp_followup_messages_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (30,),
    )
