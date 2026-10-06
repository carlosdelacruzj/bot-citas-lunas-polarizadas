from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from appointment_bot.services.telegram.constants import (
    GENERAL_RATE_LIMIT,
    MUTATION_RATE_LIMIT,
    RATE_LIMIT_WINDOW_SECONDS,
)
from appointment_bot.services.telegram.models import TelegramControlConfig


class TelegramRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, chat_id: str, *, mutation: bool, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        bucket_name = "mutation" if mutation else "general"
        limit = MUTATION_RATE_LIMIT if mutation else GENERAL_RATE_LIMIT
        events = self._events[(chat_id, bucket_name)]
        cutoff = current - RATE_LIMIT_WINDOW_SECONDS
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(current)
        return True


def _callback_is_mutation(data: str) -> bool:
    if data.startswith(
        ("wc:", "oc:", "nc:", "pq:", "py:", "wk:", "op:", "cp:", "nf:", "rf:", "pr:")
    ):
        return True
    if data.startswith(("ui:manual:", "ui:captcha:", "ui:cancel:")):
        return True
    if data.startswith("om:"):
        return data.rsplit(":", maxsplit=1)[-1] in {
            "access",
            "validate",
            "editrules",
        }
    return False


def _mutation_user_authorized(
    config: TelegramControlConfig,
    chat: dict[str, Any],
    sender: Any,
) -> bool:
    if str(chat.get("type") or "") != "private" or not isinstance(sender, dict):
        return False
    chat_id = str(chat.get("id") or "")
    user_id = str(sender.get("id") or "")
    if not chat_id or not user_id:
        return False
    if config.authorized_user_ids:
        return user_id in config.authorized_user_ids
    return user_id == chat_id and chat_id in config.authorized_chat_ids


def _command_parts(text: str) -> tuple[str | None, str]:
    stripped = text.strip()
    first, separator, arguments = stripped.partition(" ")
    if not first.startswith("/"):
        return None, ""
    command = first[1:].split("@", maxsplit=1)[0].strip().lower() or None
    return command, arguments.strip() if separator else ""
