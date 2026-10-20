from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.finance_schema import _create_finance_schema


def v25_to_v26(connection: Connection) -> None:
    _create_finance_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (26,),
    )
