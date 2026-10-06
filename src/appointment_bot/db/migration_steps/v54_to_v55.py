from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.worker_schema import _create_telegram_alert_outbox_schema


def v54_to_v55(connection: Connection) -> None:
    _create_telegram_alert_outbox_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (55,),
    )
