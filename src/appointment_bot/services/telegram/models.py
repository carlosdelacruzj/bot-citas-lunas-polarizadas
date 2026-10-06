from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TelegramControlConfig:
    bot_token: str
    authorized_chat_ids: frozenset[str]
    admin_api_url: str
    admin_api_token: str
    offset_path: Path
    poll_timeout_seconds: int
    worker_monitor_enabled: bool
    authorized_user_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PendingWorkerConfirmation:
    operation_id: str
    chat_id: str
    command: str
    expires_at: float
    opportunity_target: str | None = None
    expected_revision: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PendingOrderChange:
    operation_id: str
    chat_id: str
    action: str
    order_id: str
    original: dict[str, Any]
    updated: dict[str, Any]
    expires_at: float
    return_subject: str = "menu"


@dataclass
class RulesConversation:
    chat_id: str
    order_id: str
    original: dict[str, Any]
    updated: dict[str, Any]
    step: int
    expires_at: float


@dataclass
class NewClientConversation:
    chat_id: str
    session_id: str
    values: dict[str, Any]
    step: int
    expires_at: float


@dataclass(frozen=True)
class PendingClientCreation:
    operation_id: str
    chat_id: str
    values: dict[str, Any]
    expires_at: float


@dataclass
class SearchConversation:
    expires_at: float
    mode: str = "search"
    order_id: str | None = None
    return_subject: str = "menu"


@dataclass
class CaptchaReviewConversation:
    chat_id: str
    session_id: str
    expires_at: float
    item_token: str | None = None
    current_event_id: str | None = None
    current_image_sha256: str | None = None
    choice_answers: tuple[str, ...] = ()
    awaiting_manual_answer: bool = False
    skipped_event_ids: set[str] = field(default_factory=set)
