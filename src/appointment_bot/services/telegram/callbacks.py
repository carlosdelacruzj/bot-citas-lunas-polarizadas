from __future__ import annotations

import logging
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any

from appointment_bot.services.telegram.access import (
    TelegramRateLimiter,
    _callback_is_mutation,
    _mutation_user_authorized,
)
from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.audit import _record_audit_safe, _telegram_actor
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.captcha_conversation import (
    _clear_captcha_review_buttons,
    _process_captcha_review_callback,
)
from appointment_bot.services.telegram.client_conversation import _execute_client_creation
from appointment_bot.services.telegram.interface_callbacks import _process_interface_callback
from appointment_bot.services.telegram.models import (
    CaptchaReviewConversation,
    NewClientConversation,
    PendingClientCreation,
    PendingOrderChange,
    PendingWorkerConfirmation,
    RulesConversation,
    SearchConversation,
    TelegramControlConfig,
)
from appointment_bot.services.telegram.order_changes import (
    _execute_order_change,
    _execute_order_revalidation,
)
from appointment_bot.services.telegram.worker_controls import (
    _execute_opportunity_control,
    _execute_worker_command,
)

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _process_callback_query(
    callback_query: dict[str, Any],
    config: TelegramControlConfig,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    pending_order_changes: dict[str, PendingOrderChange],
    pending_client_creations: dict[str, PendingClientCreation],
    new_client_conversations: dict[str, NewClientConversation],
    rules_conversations: dict[str, RulesConversation],
    search_conversations: dict[str, SearchConversation],
    captcha_conversations: dict[str, CaptchaReviewConversation],
    recent_orders: dict[str, deque[str]],
    rate_limiter: TelegramRateLimiter,
    confirmation_lock: Lock,
    executor: ThreadPoolExecutor,
) -> None:
    callback_id = callback_query.get("id")
    data = callback_query.get("data")
    message = callback_query.get("message")
    chat = message.get("chat") if isinstance(message, dict) else None
    if not isinstance(callback_id, str) or not isinstance(data, str):
        return
    if not isinstance(chat, dict) or chat.get("id") is None:
        return
    chat_id = str(chat["id"])
    sender = callback_query.get("from")
    user_id = str(sender.get("id") or "") if isinstance(sender, dict) else ""
    if chat_id not in config.authorized_chat_ids:
        logger.warning("Ignored Telegram callback from an unauthorized chat.")
        _record_audit_safe(
            admin_api=admin_api,
            actor=_telegram_actor(chat_id), action="callback", status="denied"
        )
        return
    mutation = _callback_is_mutation(data)
    if mutation and not _mutation_user_authorized(config, chat, sender):
        _record_audit_safe(
            admin_api=admin_api,
            actor=_telegram_actor(chat_id, user_id),
            action="callback",
            status="denied",
            detail="Mutation requires an authorized user in a private chat.",
        )
        telegram.answer_callback_query(
            callback_id,
            "Accion permitida solo al operador autorizado en chat privado.",
        )
        return
    if not rate_limiter.allow(chat_id, mutation=mutation):
        _record_audit_safe(
            admin_api=admin_api,
            actor=_telegram_actor(chat_id), action="callback", status="rate_limited"
        )
        telegram.answer_callback_query(callback_id, "Espera un minuto y vuelve a intentar.")
        return
    if _process_captcha_review_callback(
        callback_id,
        data,
        message,
        chat_id,
        telegram,
        admin_api,
        captcha_conversations,
    ):
        return
    if _process_interface_callback(
        callback_id,
        data,
        message,
        chat_id,
        telegram,
        admin_api,
        pending_confirmations,
        pending_order_changes,
        pending_client_creations,
        new_client_conversations,
        rules_conversations,
        search_conversations,
        captcha_conversations,
        recent_orders,
        confirmation_lock,
    ):
        return
    parts = data.split(":")
    if len(parts) != 3 or parts[0] not in {"wc", "oc", "nc"} or parts[2] not in {"yes", "no"}:
        telegram.answer_callback_query(callback_id, "Accion no reconocida.")
        return
    operation_id = parts[1]
    if parts[0] == "nc":
        with confirmation_lock:
            creation = pending_client_creations.pop(operation_id, None)
        if (
            creation is None
            or creation.chat_id != chat_id
            or creation.expires_at <= time.monotonic()
        ):
            telegram.answer_callback_query(callback_id, "La confirmacion ya vencio.")
            return
        _clear_captcha_review_buttons(chat_id, message, telegram)
        if parts[2] == "no":
            _record_audit_safe(
                admin_api=admin_api,
                actor=_telegram_actor(chat_id), action="client_create",
                status="cancelled", operation_id=operation_id,
            )
            telegram.answer_callback_query(callback_id, "Operacion cancelada.")
            telegram.send_message(chat_id, "Registro cancelado. No se guardo nada.")
            return
        telegram.answer_callback_query(callback_id, "Registro confirmado.")
        _record_audit_safe(
            admin_api=admin_api,
            actor=_telegram_actor(chat_id), action="client_create",
            status="accepted", operation_id=operation_id,
        )
        executor.submit(_execute_client_creation, creation, telegram, admin_api)
        return
    if parts[0] == "oc":
        with confirmation_lock:
            change = pending_order_changes.pop(operation_id, None)
        if (
            change is None
            or change.chat_id != chat_id
            or change.expires_at <= time.monotonic()
        ):
            telegram.answer_callback_query(callback_id, "La confirmacion ya vencio.")
            return
        _clear_captcha_review_buttons(chat_id, message, telegram)
        if parts[2] == "no":
            _record_audit_safe(
                admin_api=admin_api,
                actor=_telegram_actor(chat_id), action=change.action,
                status="cancelled", target_type="service_order",
                target_id=change.order_id, operation_id=operation_id,
            )
            telegram.answer_callback_query(callback_id, "Operacion cancelada.")
            telegram.send_message(chat_id, "Operacion cancelada. No se realizaron cambios.")
            return
        telegram.answer_callback_query(callback_id, "Cambio confirmado.")
        _record_audit_safe(
            admin_api=admin_api,
            actor=_telegram_actor(chat_id), action=change.action,
            status="accepted", target_type="service_order",
            target_id=change.order_id, operation_id=operation_id,
        )
        executor.submit(_execute_order_change, change, telegram, admin_api)
        return
    with confirmation_lock:
        confirmation = pending_confirmations.pop(operation_id, None)
    if (
        confirmation is None
        or confirmation.chat_id != chat_id
        or confirmation.expires_at <= time.monotonic()
    ):
        telegram.answer_callback_query(callback_id, "La confirmacion ya vencio.")
        return
    _clear_captcha_review_buttons(chat_id, message, telegram)
    if parts[2] == "no":
        _record_audit_safe(
            admin_api=admin_api,
            actor=_telegram_actor(chat_id), action=confirmation.command,
            status="cancelled", operation_id=operation_id,
        )
        telegram.answer_callback_query(callback_id, "Operacion cancelada.")
        telegram.send_message(chat_id, "Operacion cancelada. No se realizaron cambios.")
        return
    telegram.answer_callback_query(callback_id, "Solicitud confirmada.")
    is_opportunity_control = confirmation.command.startswith("opportunity:")
    _record_audit_safe(
        admin_api=admin_api,
        actor=_telegram_actor(chat_id), action=confirmation.command,
        status="accepted",
        target_type="opportunity_control" if is_opportunity_control else None,
        target_id=confirmation.opportunity_target,
        operation_id=operation_id,
    )
    if is_opportunity_control:
        executor.submit(
            _execute_opportunity_control,
            confirmation,
            telegram,
            admin_api,
        )
        return
    if confirmation.command.startswith("revalidate:"):
        executor.submit(
            _execute_order_revalidation,
            confirmation,
            telegram,
            admin_api,
        )
        return
    executor.submit(
        _execute_worker_command,
        confirmation,
        telegram,
        admin_api,
    )
