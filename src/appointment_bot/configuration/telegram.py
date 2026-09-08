from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramSettings:
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_notify_unavailable: bool
