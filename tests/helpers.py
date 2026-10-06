from __future__ import annotations

import atexit
import os
import uuid
from contextlib import contextmanager
from dataclasses import fields, make_dataclass, replace
from functools import cached_property
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlsplit, urlunsplit

from dotenv import load_dotenv
from psycopg import sql

from appointment_bot.configuration.captcha import CaptchaSettings
from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.configuration.loading import load_settings
from appointment_bot.configuration.reservation import ReservationSettings
from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.configuration.telegram import TelegramSettings
from appointment_bot.configuration.whatsapp import WhatsappSettings
from appointment_bot.db.common import _connection

_GROUP_TYPES = {
    "runtime": RuntimeSettings,
    "reservation": ReservationSettings,
    "captcha": CaptchaSettings,
    "evidence": EvidenceSettings,
    "telegram": TelegramSettings,
    "whatsapp": WhatsappSettings,
}


def _group_property(group_type):
    return cached_property(
        lambda configuration: group_type(
            **{field.name: getattr(configuration, field.name) for field in fields(group_type)}
        )
    )


# A flat fixture keeps existing replace scenarios independent of production composition.
TestConfiguration = make_dataclass(
    "TestConfiguration",
    [
        (field.name, field.type)
        for group_type in _GROUP_TYPES.values()
        for field in fields(group_type)
    ],
    frozen=True,
    repr=False,
    namespace={name: _group_property(group_type) for name, group_type in _GROUP_TYPES.items()},
)

_CREATED_SCHEMAS: list[tuple[str, str]] = []


def _test_database_url() -> str:
    load_dotenv()
    value = os.getenv("APPOINTMENT_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("APPOINTMENT_DATABASE_URL is required for database tests.")
    return value


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = parts.query
    option = f"options={quote(f'-csearch_path={schema}', safe='')}"
    query = f"{query}&{option}" if query else option
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def make_settings(root: Path) -> TestConfiguration:
    database_url = _test_database_url()
    schema = f"test_{uuid.uuid4().hex}"
    with _connection(database_url) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    _CREATED_SCHEMAS.append((database_url, schema))
    with patch.dict(
        "os.environ",
        {
            "TARGET_URL": "https://example.invalid",
            "LOGIN_USERNAME": "test-only-user",
            "LOGIN_PASSWORD": "test-only-password",
            "APIKEY_2CAPTCHA": "test-only-captcha-key",
            "APPOINTMENT_DATABASE_URL": _schema_url(database_url, schema),
            "APPOINTMENT_CREDENTIAL_KEYS": ("MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="),
            "TELEGRAM_BOT_TOKEN": "test-only-token",
            "TELEGRAM_CHAT_ID": "123456789",
            "TELEGRAM_ENABLED": "true",
            "CONTINUOUS_WORKER_ENABLED": "true",
            "AUTO_RESERVE": "true",
            "CLIENT_VIDEO_WIDTH": "1920",
            "CLIENT_VIDEO_HEIGHT": "1080",
            "RECORD_CLIENT_SESSIONS": "false",
            "RECORD_CLIENT_VIDEO_FINAL_MP4": "true",
        },
        clear=False,
    ):
        groups = load_settings(require_login=False)
        settings = TestConfiguration(
            **{
                field.name: getattr(group, field.name)
                for group in groups
                for field in fields(group)
            }
        )
    return replace(
        settings,
        logs_dir=root / "logs",
        screenshots_dir=root / "screenshots",
        client_videos_dir=root / "videos" / "reservations",
        cleanup_retention_days=14,
    )


@contextmanager
def database_connection(settings: TestConfiguration):
    with _connection(settings.database_url) as connection:
        yield connection


def _cleanup_test_schemas() -> None:
    while _CREATED_SCHEMAS:
        database_url, schema = _CREATED_SCHEMAS.pop()
        try:
            with _connection(database_url) as connection:
                connection.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
                )
        except Exception:
            pass


atexit.register(_cleanup_test_schemas)
