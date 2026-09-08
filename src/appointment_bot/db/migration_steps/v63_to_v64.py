from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.template_schema import (
    _create_whatsapp_followup_template_trace_schema,
)


def v63_to_v64(connection: Connection) -> None:
    _create_whatsapp_followup_template_trace_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (64,),
    )
