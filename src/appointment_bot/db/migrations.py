"""Compatibility exports for schema creation and migration."""

from appointment_bot.services.database_migrations import (
    SCHEMA_VERSION,
    create_current_schema,
    migrate_database,
)

__all__ = ["SCHEMA_VERSION", "create_current_schema", "migrate_database"]
