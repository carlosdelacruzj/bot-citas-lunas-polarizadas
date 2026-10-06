from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.reservation_schema import (
    _create_reservation_program_identity_schema,
)


def v48_to_v49(connection: Connection) -> None:
    _create_reservation_program_identity_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (49,),
    )
