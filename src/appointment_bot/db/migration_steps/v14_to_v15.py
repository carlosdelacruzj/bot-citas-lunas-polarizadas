from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.order_schema import _create_order_checks_schema


def v14_to_v15(connection: Connection) -> None:
    _create_order_checks_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (15,),
    )
