from __future__ import annotations

import logging
import secrets
import time
from threading import Lock
from typing import Any

from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.constants import (
    CONFIRMATION_TTL_SECONDS,
    CONVERSATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.models import PendingOrderChange, RulesConversation
from appointment_bot.services.telegram.order_changes import (
    _send_order_change_confirmation,
    _store_order_change,
)
from appointment_bot.services.telegram.presentation import format_order_rules
from appointment_bot.services.telegram.state import _cancel_chat_order_state_unlocked
from appointment_bot.services.telegram.validation import (
    _parse_rules_step,
    _rules_payload,
    _valid_order_id,
    _validate_rules_payload,
)

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _start_rules_conversation(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    rules_conversations: dict[str, RulesConversation],
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> None:
    order_id = arguments.strip()
    if not _valid_order_id(order_id):
        telegram.send_message(chat_id, "Uso: /reglas_editar ORDER_ID")
        return
    try:
        order = next(
            (item for item in admin_api.get_service_orders() if item.get("order_id") == order_id),
            None,
        )
    except TelegramControlError as exc:
        logger.warning("Could not start rules conversation: %s", exc)
        telegram.send_message(chat_id, "No pude consultar esa orden.")
        return
    if order is None:
        telegram.send_message(chat_id, "No pude encontrar esa orden.")
        return
    original = _rules_payload(order)
    conversation = RulesConversation(
        chat_id=chat_id,
        order_id=order_id,
        original=original,
        updated=dict(original),
        step=0,
        expires_at=time.monotonic() + CONVERSATION_TTL_SECONDS,
    )
    with confirmation_lock:
        _cancel_chat_order_state_unlocked(
            chat_id,
            pending_order_changes,
            rules_conversations,
        )
        rules_conversations[chat_id] = conversation
    telegram.send_message(
        chat_id,
        f"EDITAR REGLAS\n\n{format_order_rules(order)}\n\n{_rules_step_prompt(0)}",
        reply_markup=_rules_prompt_markup(0),
    )


def _process_rules_conversation_message(
    chat_id: str,
    text: str,
    telegram: TelegramBotApi,
    rules_conversations: dict[str, RulesConversation],
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        conversation = rules_conversations.get(chat_id)
    if conversation is None:
        return False
    if conversation.expires_at <= time.monotonic():
        with confirmation_lock:
            rules_conversations.pop(chat_id, None)
        telegram.send_message(chat_id, "La edicion de reglas vencio. Inicia nuevamente.")
        return True
    return _continue_rules_conversation(
        conversation,
        text,
        telegram,
        rules_conversations,
        pending_order_changes,
        confirmation_lock,
    )


def _continue_rules_conversation(
    conversation: RulesConversation,
    text: str,
    telegram: TelegramBotApi,
    rules_conversations: dict[str, RulesConversation],
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> bool:
    chat_id = conversation.chat_id
    try:
        field, value = _parse_rules_step(conversation.step, text, conversation.updated)
    except ValueError as exc:
        telegram.send_message(
            chat_id,
            f"{exc}\n\n{_rules_step_prompt(conversation.step)}",
            reply_markup=_rules_prompt_markup(conversation.step),
        )
        return True
    conversation.updated[field] = value
    conversation.step += 1
    conversation.expires_at = time.monotonic() + CONVERSATION_TTL_SECONDS
    if conversation.step < 4:
        telegram.send_message(
            chat_id,
            _rules_step_prompt(conversation.step),
            reply_markup=_rules_prompt_markup(conversation.step),
        )
        return True
    try:
        _validate_rules_payload(conversation.updated)
    except ValueError as exc:
        with confirmation_lock:
            rules_conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            f"No se guardo ningun cambio: {exc}\nInicia nuevamente con /reglas_editar.",
        )
        return True
    with confirmation_lock:
        rules_conversations.pop(chat_id, None)
    if conversation.updated == conversation.original:
        telegram.send_message(chat_id, "No hay cambios en las reglas.")
        return True
    change = PendingOrderChange(
        operation_id=secrets.token_hex(6),
        chat_id=chat_id,
        action="rules",
        order_id=conversation.order_id,
        original=conversation.original,
        updated=conversation.updated,
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
    )
    _store_order_change(change, pending_order_changes, confirmation_lock)
    _send_order_change_confirmation(change, telegram)
    return True


def _rules_step_prompt(step: int) -> str:
    return (
        "Paso 1/4 - Fecha minima. Responde DD-MM-YYYY, mantener o sin limite.",
        "Paso 2/4 - Fecha maxima. Responde DD-MM-YYYY, mantener o sin limite.",
        "Paso 3/4 - Dias permitidos. Usa los botones o responde 1,2,...7.",
        "Paso 4/4 - Fechas excluidas. Usa DD-MM-YYYY al DD-MM-YYYY; "
        "separa varios rangos con ; o elige Sin exclusiones.",
    )[step]


def _rules_prompt_markup(step: int) -> dict[str, Any]:
    if step in {0, 1}:
        rows = [[
            {"text": "Mantener", "callback_data": "rf:value:keep"},
            {"text": "Quitar limite", "callback_data": "rf:value:clear"},
        ]]
    elif step == 2:
        rows = [
            [
                {"text": "Lun-Vie", "callback_data": "rf:days:mon_fri"},
                {"text": "Lun-Sab", "callback_data": "rf:days:mon_sat"},
            ],
            [{"text": "Solo sabado", "callback_data": "rf:days:sat"}],
            [
                {"text": "Todos", "callback_data": "rf:value:clear"},
                {"text": "Mantener", "callback_data": "rf:value:keep"},
            ],
        ]
    else:
        rows = [[
            {"text": "Sin exclusiones", "callback_data": "rf:value:clear"},
            {"text": "Mantener", "callback_data": "rf:value:keep"},
        ]]
    if step > 0:
        rows.append([{"text": "Atras", "callback_data": "rf:nav:back"}])
    rows.append([{"text": "Cancelar", "callback_data": "ui:cancel:guided"}])
    return {"inline_keyboard": rows}
