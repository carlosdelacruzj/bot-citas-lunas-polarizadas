from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlsplit, urlunsplit

from dotenv import load_dotenv

from appointment_bot.config import Settings, load_settings
from appointment_bot.services import postgres_database


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


def make_settings(root: Path) -> Settings:
    database_url = _test_database_url()
    schema = f"test_{uuid.uuid4().hex}"
    with postgres_database._connection(database_url) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')
    with patch.dict(
        "os.environ",
        {
            "TARGET_URL": "https://example.invalid",
            "APPOINTMENT_DATABASE_URL": _schema_url(database_url, schema),
            "CONTINUOUS_WORKER_ENABLED": "true",
            "AUTO_RESERVE": "true",
        },
        clear=False,
    ):
        settings = load_settings(require_login=False)
    return replace(
        settings,
        logs_dir=root / "logs",
        screenshots_dir=root / "screenshots",
        diagnostics_dir=root / "diagnostics",
        state_dir=root / "state",
        cleanup_retention_days=14,
    )


@contextmanager
def database_connection(settings: Settings):
    with postgres_database._connection(settings.database_url) as connection:
        yield connection
