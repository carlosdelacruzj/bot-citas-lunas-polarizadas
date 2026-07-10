from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from psycopg import Connection

from appointment_bot.config import Settings, load_settings
from appointment_bot.db.migrations import migrate_database
from appointment_bot.db.pool import pooled_connection
from appointment_bot.services.credential_cipher import CredentialCipher

DEFAULT_RESERVATION_AMOUNT = Decimal("40.00")
_INITIALIZED_URLS: set[str] = set()
_INITIALIZATION_LOCK = threading.Lock()

def init_database(settings: Settings | None = None) -> None:
    settings = _settings(settings)
    database_url = _database_url(settings)
    if database_url in _INITIALIZED_URLS:
        return

    with _INITIALIZATION_LOCK:
        if database_url in _INITIALIZED_URLS:
            return
        with _connection(database_url) as connection:
            migrate_database(connection)
        _INITIALIZED_URLS.add(database_url)


def _settings(settings: Settings | None) -> Settings:
    return settings or load_settings(require_login=False)


def _database_url(settings: Settings) -> str:
    if not settings.database_url:
        raise ValueError("APPOINTMENT_DATABASE_URL is required for PostgreSQL.")
    return settings.database_url


def _credential_cipher(settings: Settings) -> CredentialCipher:
    return CredentialCipher(settings.credential_encryption_keys)


@contextmanager
def _connection(database_url: str) -> Iterator[Connection]:
    with pooled_connection(database_url) as connection:
        yield connection


@contextmanager
def _operation_connection(
    settings: Settings,
    connection: Connection | None,
) -> Iterator[Connection]:
    if connection is not None:
        yield connection
        return
    with _connection(_database_url(settings)) as managed_connection:
        yield managed_connection


def _executemany(connection: Connection, query: str, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    with connection.cursor() as cursor:
        cursor.executemany(query, rows)


def _id_from_value(prefix: str, value: str) -> str:
    normalized = value.strip().lower()
    safe = "".join(character for character in normalized if character.isalnum()) or "item"
    if safe == normalized and len(safe) <= 32:
        return f"{prefix}-{safe}"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{safe[:15]}-{digest}"


def _normalize_phone(value: str) -> str:
    return "".join(character for character in value if character.isdigit() or character == "+")


def _mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) <= 4:
        return "***"
    return f"***{digits[-4:]}"


def _decimal_or_none(value: str | float | int | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _decimal_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _detail_text(details: dict[str, Any], key: str) -> str | None:
    value = details.get(key)
    if value in {None, ""}:
        return None
    return str(value)


def _optional_text_value(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _parse_minimum_reservation_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("minimum_reservation_date must use YYYY-MM-DD or DD/MM/YYYY.")


def _parse_allowed_weekdays(value: Iterable[int] | None) -> list[int] | None:
    if value is None:
        return None
    days = sorted({int(day) for day in value})
    if not days:
        return None
    invalid = [day for day in days if day < 1 or day > 7]
    if invalid:
        raise ValueError("allowed_weekdays must use ISO days from 1 to 7.")
    return days


def _mask_username(username: str) -> str:
    if not username:
        return ""
    if len(username) <= 3:
        return "***"
    return f"{username[:2]}***{username[-1]}"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _timestamp_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
