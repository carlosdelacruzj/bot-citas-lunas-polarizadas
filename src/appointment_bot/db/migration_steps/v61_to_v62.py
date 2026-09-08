from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.template_schema import (
    _create_whatsapp_automation_template_trace_schema,
)


def v61_to_v62(connection: Connection) -> None:
    _create_whatsapp_automation_template_trace_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (62,),
    )
