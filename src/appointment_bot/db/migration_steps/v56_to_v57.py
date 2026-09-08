from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.reminder_schema import (
    _create_appointment_reminder_control_schema,
)


def v56_to_v57(connection: Connection) -> None:
    _create_appointment_reminder_control_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (57,),
    )
