"""Compatibility exports for database initialization."""

from appointment_bot.services.postgres_common import init_database

__all__ = ["init_database"]
