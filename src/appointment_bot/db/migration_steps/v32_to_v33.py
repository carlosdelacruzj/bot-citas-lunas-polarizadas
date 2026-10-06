from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.worker_schema import _create_remote_control_audit_schema


def v32_to_v33(connection: Connection) -> None:
    _create_remote_control_audit_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (33,),
    )
