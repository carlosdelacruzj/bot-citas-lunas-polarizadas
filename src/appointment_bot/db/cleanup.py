from __future__ import annotations

from datetime import UTC, datetime, timedelta

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _settings,
    init_database,
)


def cleanup_database_history(settings: Settings | None = None) -> None:
    settings = _settings(settings)
    init_database(settings)
    cutoff = (datetime.now(UTC) - timedelta(days=settings.cleanup_retention_days)).isoformat(
        timespec="seconds"
    )
    with _connection(_database_url(settings)) as connection:
        connection.execute("DELETE FROM runs WHERE created_at < %s", (cutoff,))
        connection.execute("DELETE FROM order_checks WHERE checked_at < %s", (cutoff,))

