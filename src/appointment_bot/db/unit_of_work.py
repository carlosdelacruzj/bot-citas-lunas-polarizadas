from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection

from appointment_bot.config import Settings
from appointment_bot.db.common import _operation_connection, init_database


@contextmanager
def postgres_unit_of_work(
    settings: Settings,
    connection_override: Connection | None = None,
) -> Iterator[Connection]:
    """Own one PostgreSQL transaction unless an outer transaction was supplied."""
    init_database(settings)
    with _operation_connection(settings, connection_override) as connection:
        yield connection
