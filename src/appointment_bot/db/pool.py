from __future__ import annotations

import atexit
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_POOLS: dict[str, ConnectionPool] = {}
_POOLS_LOCK = threading.Lock()


@contextmanager
def pooled_connection(database_url: str) -> Iterator[Connection]:
    with _pool(database_url).connection() as connection:
        yield connection


def _pool(database_url: str) -> ConnectionPool:
    pool = _POOLS.get(database_url)
    if pool is not None:
        return pool
    with _POOLS_LOCK:
        pool = _POOLS.get(database_url)
        if pool is None:
            pool = ConnectionPool(
                conninfo=database_url,
                min_size=0,
                max_size=10,
                timeout=10,
                kwargs={"row_factory": dict_row},
                open=True,
            )
            _POOLS[database_url] = pool
        return pool


def close_connection_pools() -> None:
    with _POOLS_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.close()


atexit.register(close_connection_pools)
