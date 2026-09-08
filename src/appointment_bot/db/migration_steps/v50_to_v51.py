from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.captcha_schema import _create_captcha_authority_schema


def v50_to_v51(connection: Connection) -> None:
    _create_captcha_authority_schema(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (51,),
    )
