from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.worker_schema import _create_worker_commands_schema


def v22_to_v23(connection: Connection) -> None:
    _create_worker_commands_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (23,),
    )
