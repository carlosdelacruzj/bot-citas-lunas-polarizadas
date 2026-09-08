from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.finance_schema import _create_finance_month_closure_schema


def v51_to_v52(connection: Connection) -> None:
    _create_finance_month_closure_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (52,),
    )
