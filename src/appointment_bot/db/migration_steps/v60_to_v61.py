from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.template_schema import (
    _create_whatsapp_message_template_schema,
)


def v60_to_v61(connection: Connection) -> None:
    _create_whatsapp_message_template_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (61,),
    )
