from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.opportunity_schema import (
    _create_opportunity_observability_schema,
)


def v49_to_v50(connection: Connection) -> None:
    _create_opportunity_observability_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (50,),
    )
