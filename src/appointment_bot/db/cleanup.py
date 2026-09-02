from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _settings,
    init_database,
)

CAPTCHA_SHADOW_RETENTION_DAYS: Final = 14
WORKER_COMMAND_RETENTION_DAYS: Final = 90


def cleanup_database_history(settings: Settings | None = None) -> dict[str, int]:
    settings = _settings(settings)
    init_database(settings)
    now = datetime.now(UTC)
    history_cutoff = now - timedelta(days=settings.cleanup_retention_days)
    captcha_shadow_cutoff = now - timedelta(days=CAPTCHA_SHADOW_RETENTION_DAYS)
    worker_command_cutoff = now - timedelta(days=WORKER_COMMAND_RETENTION_DAYS)
    removed: dict[str, int] = {}

    statements = (
        ("runs", "DELETE FROM runs WHERE created_at < %s", history_cutoff),
        (
            "order_checks",
            "DELETE FROM order_checks WHERE checked_at < %s",
            history_cutoff,
        ),
        (
            "whatsapp_test_messages",
            """
            DELETE FROM whatsapp_messages
            WHERE test_mode = true AND prepared_at < %s
            """,
            history_cutoff,
        ),
        (
            "whatsapp_test_followups",
            """
            DELETE FROM whatsapp_followup_messages
            WHERE test_mode = true AND prepared_at < %s
            """,
            history_cutoff,
        ),
        (
            "captcha_shadow_processed",
            """
            DELETE FROM captcha_shadow_outbox
            WHERE status = 'processed' AND processed_at < %s
            """,
            captcha_shadow_cutoff,
        ),
        (
            "worker_commands_applied",
            """
            DELETE FROM worker_commands
            WHERE status = 'applied' AND processed_at < %s
            """,
            worker_command_cutoff,
        ),
    )

    with _connection(_database_url(settings)) as connection:
        for label, statement, cutoff in statements:
            cursor = connection.execute(statement, (cutoff,))
            removed[label] = max(cursor.rowcount, 0)
    return removed
