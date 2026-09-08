from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.order_schema import _create_observer_window_metrics_schema


def v17_to_v18(connection: Connection) -> None:
    _create_observer_window_metrics_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (18,),
    )
