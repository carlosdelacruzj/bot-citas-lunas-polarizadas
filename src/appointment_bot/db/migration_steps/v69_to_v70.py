from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.template_schema import (
    _freeze_historical_whatsapp_followup_text,
)


def v69_to_v70(connection: Connection) -> None:
    _freeze_historical_whatsapp_followup_text(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (70,),
    )
