from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.captcha_schema import (
    _create_captcha_sampling_control_schema,
)


def v46_to_v47(connection: Connection) -> None:
    _create_captcha_sampling_control_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (47,),
    )
