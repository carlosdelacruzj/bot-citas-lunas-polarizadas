from __future__ import annotations

from psycopg import Connection


def v37_to_v38(connection: Connection) -> None:
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (38,),
    )
