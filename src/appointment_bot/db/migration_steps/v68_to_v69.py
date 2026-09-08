from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.template_schema import (
    _retire_appointment_reminder_legacy_schema,
)


def v68_to_v69(connection: Connection) -> None:
    _retire_appointment_reminder_legacy_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (69,),
    )
