from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.template_schema import (
    _unify_appointment_reminder_template_schema,
)


def v64_to_v65(connection: Connection) -> None:
    _unify_appointment_reminder_template_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (65,),
    )
