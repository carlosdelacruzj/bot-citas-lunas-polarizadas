"""Public database facade for the migration target package."""

from appointment_bot.db.connection import init_database
from appointment_bot.db.migrations import SCHEMA_VERSION, create_current_schema, migrate_database

__all__ = [
    "SCHEMA_VERSION",
    "create_current_schema",
    "init_database",
    "migrate_database",
]
