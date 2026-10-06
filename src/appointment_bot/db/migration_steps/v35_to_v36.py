from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.whatsapp_legacy import (
    create_legacy_whatsapp_automation_jobs_schema,
)


def v35_to_v36(connection: Connection) -> None:
    create_legacy_whatsapp_automation_jobs_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (36,),
    )
