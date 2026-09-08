from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from appointment_bot.configuration.telegram import TelegramSettings
from appointment_bot.services.telegram.constants import (
    DEFAULT_ADMIN_API_URL,
    DEFAULT_POLL_TIMEOUT_SECONDS,
)
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.models import TelegramControlConfig


def load_control_config(telegram_settings: TelegramSettings) -> TelegramControlConfig:
    if not telegram_settings.telegram_enabled:
        raise TelegramControlError("Telegram is disabled.")
    chat_ids_text = os.getenv("TELEGRAM_CONTROL_CHAT_IDS", "").strip()
    chat_ids = {
        item.strip()
        for item in (
            chat_ids_text.split(",") if chat_ids_text else [telegram_settings.telegram_chat_id]
        )
        if item.strip()
    }
    if not chat_ids:
        raise TelegramControlError("No authorized Telegram chat_id is configured.")
    user_ids = frozenset(
        item.strip()
        for item in os.getenv("TELEGRAM_CONTROL_USER_IDS", "").split(",")
        if item.strip()
    )
    admin_api_token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
    if not admin_api_token:
        raise TelegramControlError("APPOINTMENT_BOT_API_TOKEN is required.")
    workdir = Path(os.getenv("APPOINTMENT_BOT_WORKDIR", "").strip() or Path.cwd())
    offset_text = os.getenv("TELEGRAM_CONTROL_OFFSET_PATH", "").strip()
    offset_path = (
        Path(offset_text) if offset_text else workdir / ".runtime/telegram-control-offset.json"
    )
    poll_timeout = _positive_int(
        os.getenv("TELEGRAM_CONTROL_POLL_TIMEOUT_SECONDS"),
        default=DEFAULT_POLL_TIMEOUT_SECONDS,
    )
    return TelegramControlConfig(
        bot_token=telegram_settings.telegram_bot_token,
        authorized_chat_ids=frozenset(chat_ids),
        authorized_user_ids=user_ids,
        admin_api_url=_validated_admin_api_url(
            os.getenv("TELEGRAM_CONTROL_ADMIN_API_URL", DEFAULT_ADMIN_API_URL)
        ),
        admin_api_token=admin_api_token,
        offset_path=offset_path,
        poll_timeout_seconds=poll_timeout,
        worker_monitor_enabled=os.getenv(
            "TELEGRAM_WORKER_MONITOR_ENABLED",
            "false",
        )
        .strip()
        .lower()
        in {"1", "true", "yes", "on"},
    )


def _validated_admin_api_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.username or parsed.password or not parsed.hostname:
        raise TelegramControlError("TELEGRAM_CONTROL_ADMIN_API_URL is invalid.")
    loopback = parsed.hostname.lower() in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme == "http" and loopback:
        return normalized
    if parsed.scheme == "https":
        return normalized
    raise TelegramControlError("TELEGRAM_CONTROL_ADMIN_API_URL must use loopback HTTP or HTTPS.")


def _positive_int(value: str | None, *, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise TelegramControlError(f"Invalid positive integer: {value!r}") from exc
    if parsed < 1:
        raise TelegramControlError(f"Integer must be positive: {value!r}")
    return parsed
