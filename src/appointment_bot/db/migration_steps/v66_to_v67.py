from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.post_appointment_schema import (
    _create_post_appointment_schema,
)


def v66_to_v67(connection: Connection) -> None:
    _create_post_appointment_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (67,),
    )
