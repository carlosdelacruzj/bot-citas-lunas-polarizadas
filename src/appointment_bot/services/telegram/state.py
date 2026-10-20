from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from threading import Lock
from typing import Any

from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.models import (
    CaptchaReviewConversation,
    NewClientConversation,
    PendingClientCreation,
    PendingOrderChange,
    PendingWorkerConfirmation,
    RulesConversation,
)
from appointment_bot.services.telegram.presentation import _main_menu_markup

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _cancel_chat_confirmations(
    chat_id: str,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        return _cancel_chat_confirmations_unlocked(chat_id, pending_confirmations)


def _cancel_chat_confirmations_unlocked(
    chat_id: str,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
) -> bool:
    operation_ids = [
        operation_id
        for operation_id, confirmation in pending_confirmations.items()
        if confirmation.chat_id == chat_id
    ]
    for operation_id in operation_ids:
        pending_confirmations.pop(operation_id, None)
    return bool(operation_ids)


def _cancel_pending_client_creation_unlocked(
    chat_id: str,
    pending_creations: dict[str, PendingClientCreation],
) -> bool:
    operation_ids = [
        operation_id
        for operation_id, creation in pending_creations.items()
        if creation.chat_id == chat_id
    ]
    for operation_id in operation_ids:
        pending_creations.pop(operation_id, None)
    return bool(operation_ids)


def _remove_expired_confirmations(
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    confirmation_lock: Lock,
) -> None:
    now = time.monotonic()
    with confirmation_lock:
        expired = [
            operation_id
            for operation_id, confirmation in pending_confirmations.items()
            if confirmation.expires_at <= now
        ]
        for operation_id in expired:
            pending_confirmations.pop(operation_id, None)


def _cancel_chat_order_state(
    chat_id: str,
    pending_order_changes: dict[str, PendingOrderChange],
    rules_conversations: dict[str, RulesConversation],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        return _cancel_chat_order_state_unlocked(
            chat_id,
            pending_order_changes,
            rules_conversations,
        )


def _cancel_chat_order_state_unlocked(
    chat_id: str,
    pending_order_changes: dict[str, PendingOrderChange],
    rules_conversations: dict[str, RulesConversation],
) -> bool:
    operation_ids = [
        operation_id
        for operation_id, change in pending_order_changes.items()
        if change.chat_id == chat_id
    ]
    for operation_id in operation_ids:
        pending_order_changes.pop(operation_id, None)
    conversation_removed = rules_conversations.pop(chat_id, None) is not None
    return bool(operation_ids) or conversation_removed


def _remove_expired_order_state(
    pending_order_changes: dict[str, PendingOrderChange],
    rules_conversations: dict[str, RulesConversation],
    confirmation_lock: Lock,
) -> None:
    now = time.monotonic()
    with confirmation_lock:
        expired_changes = [
            operation_id
            for operation_id, change in pending_order_changes.items()
            if change.expires_at <= now
        ]
        for operation_id in expired_changes:
            pending_order_changes.pop(operation_id, None)
        expired_chats = [
            chat_id
            for chat_id, conversation in rules_conversations.items()
            if conversation.expires_at <= now
        ]
        for chat_id in expired_chats:
            rules_conversations.pop(chat_id, None)


def _cancel_chat_client_state(
    chat_id: str,
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        removed = conversations.pop(chat_id, None) is not None
        return _cancel_pending_client_creation_unlocked(
            chat_id,
            pending_creations,
        ) or removed


def _remove_expired_client_state(
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    telegram: TelegramBotApi,
    confirmation_lock: Lock,
) -> None:
    now = time.monotonic()
    with confirmation_lock:
        expired_chats = [
            chat_id
            for chat_id, conversation in conversations.items()
            if conversation.expires_at <= now
        ]
        for chat_id in expired_chats:
            conversations.pop(chat_id, None)
        expired_operations = [
            operation_id
            for operation_id, creation in pending_creations.items()
            if creation.expires_at <= now
        ]
        expired_confirmation_chats = {
            pending_creations[operation_id].chat_id
            for operation_id in expired_operations
        }
        for operation_id in expired_operations:
            pending_creations.pop(operation_id, None)
    for chat_id in expired_chats:
        telegram.send_message(
            chat_id,
            "El alta manual vencio por inactividad. No se creo ni guardo nada.",
            reply_markup=_main_menu_markup(),
        )
    for chat_id in expired_confirmation_chats:
        telegram.send_message(
            chat_id,
            "La confirmacion vencio. No se creo ni guardo ningun cliente.",
            reply_markup=_main_menu_markup(),
        )


def _remove_expired_captcha_state(
    conversations: dict[str, CaptchaReviewConversation],
    telegram: TelegramBotApi,
) -> None:
    now = time.monotonic()
    expired_chats = [
        chat_id
        for chat_id, conversation in conversations.items()
        if conversation.expires_at <= now
    ]
    for chat_id in expired_chats:
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "La sesion de CAPTCHA vencio despues de 10 minutos sin actividad.",
            reply_markup=_main_menu_markup(),
        )


def _update_id(update: dict[str, Any]) -> int | None:
    value = update.get("update_id")
    return value if isinstance(value, int) and value >= 0 else None


def _load_next_offset(path: Path) -> int | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("next_offset")
        return value if isinstance(value, int) and value >= 0 else None
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring an invalid Telegram control offset file.")
        return None


def _store_next_offset(path: Path, next_offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps({"next_offset": next_offset}) + "\n", encoding="utf-8")
    temporary.replace(path)
