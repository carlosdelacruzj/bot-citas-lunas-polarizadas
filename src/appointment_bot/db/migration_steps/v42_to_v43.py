from __future__ import annotations

from psycopg import Connection


def v42_to_v43(connection: Connection) -> None:
    connection.execute("DROP TABLE IF EXISTS hosted_registration_contacts")
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (43,),
    )
