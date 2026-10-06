from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.opportunity_schema import _promote_stable_runtime_schema


def v67_to_v68(connection: Connection) -> None:
    _promote_stable_runtime_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (68,),
    )
