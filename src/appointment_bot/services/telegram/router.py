from __future__ import annotations

import logging
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any

from appointment_bot.services.telegram.access import (
    TelegramRateLimiter,
    _command_parts,
    _mutation_user_authorized,
)
from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.audit import (
    _audit_target,
    _record_audit_safe,
    _telegram_actor,
)
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.callbacks import _process_callback_query
from appointment_bot.services.telegram.captcha_conversation import (
    _process_captcha_review_message,
    _start_captcha_review,
)
from appointment_bot.services.telegram.client_conversation import (
    _delete_message_safe,
    _process_new_client_message,
    _start_new_client_conversation,
)
from appointment_bot.services.telegram.constants import (
    CONVERSATION_TTL_SECONDS,
    HELP_TEXT,
    MUTATING_COMMANDS,
    ORDER_TARGET_COMMANDS,
)
from appointment_bot.services.telegram.errors import TelegramControlError
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
    _request_credentials_change,
    _request_payment_change,
    _request_priority_change,
)
from appointment_bot.services.telegram.panels import (
    _send_clients,
    _send_daily_summary,
    _send_main_menu,
    _send_order_query,
    _send_pending_attention,
    _send_pending_payments,
    _send_queue,
    _send_recent_errors,
    _send_search_results,
)
from appointment_bot.services.telegram.presentation import _main_menu_markup
from appointment_bot.services.telegram.rules_conversation import (
    _process_rules_conversation_message,
    _start_rules_conversation,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_client_state,
    _cancel_chat_confirmations,
    _cancel_chat_order_state,
    _cancel_pending_client_creation_unlocked,
)
from appointment_bot.services.telegram.worker_controls import _request_worker_confirmation
from appointment_bot.services.telegram.worker_panels import (
    _send_opportunity_panel,
    _send_worker_panel,
)

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _process_update(
    update: dict[str, Any],
    config: TelegramControlConfig,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    *,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    pending_order_changes: dict[str, PendingOrderChange],
    rules_conversations: dict[str, RulesConversation],
    new_client_conversations: dict[str, NewClientConversation],
    pending_client_creations: dict[str, PendingClientCreation],
    search_conversations: dict[str, SearchConversation],
    captcha_conversations: dict[str, CaptchaReviewConversation],
    recent_orders: dict[str, deque[str]],
    rate_limiter: TelegramRateLimiter,
    confirmation_lock: Lock,
    executor: ThreadPoolExecutor,
) -> None:
    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        _process_callback_query(
            callback_query,
            config,
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
            rate_limiter,
            confirmation_lock,
            executor,
        )
        return
    message = update.get("message")
    if not isinstance(message, dict):
        return
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return
    chat_id = str(chat["id"])
    sender = message.get("from")
    user_id = str(sender.get("id") or "") if isinstance(sender, dict) else ""
    if chat_id not in config.authorized_chat_ids:
        logger.warning("Ignored Telegram update from an unauthorized chat.")
        _record_audit_safe(
            admin_api=admin_api,
            actor=_telegram_actor(chat_id), action="message", status="denied"
        )
        return
    text = message.get("text")
    if not isinstance(text, str):
        return
    if not text.strip().startswith("/"):
        active_search = search_conversations.get(chat_id)
        guided_mutation = (
            chat_id in captcha_conversations
            or chat_id in new_client_conversations
            or chat_id in rules_conversations
            or (
                active_search is not None
                and active_search.mode in {"credentials", "payment"}
            )
        )
        if not rate_limiter.allow(chat_id, mutation=guided_mutation):
            _record_audit_safe(
                admin_api=admin_api,
                actor=_telegram_actor(chat_id),
                action="conversation_reply",
                status="rate_limited",
            )
            telegram.send_message(
                chat_id,
                "Estas respondiendo demasiado rapido. Espera un minuto para continuar.",
            )
            return
        search = search_conversations.get(chat_id)
        if chat_id in captcha_conversations and not _mutation_user_authorized(
            config, chat, sender
        ):
            telegram.send_message(
                chat_id,
                "El etiquetado solo se permite al operador autorizado en chat privado.",
            )
            return
        if _process_captcha_review_message(
            chat_id,
            text,
            telegram,
            admin_api,
            captcha_conversations,
        ):
            return
        if search is not None:
            if search.expires_at <= time.monotonic():
                search_conversations.pop(chat_id, None)
                telegram.send_message(
                    chat_id,
                    (
                        "La correccion de acceso vencio. Abre nuevamente el cliente."
                        if search.mode == "credentials"
                        else "El registro del abono vencio. Abre nuevamente el cobro."
                        if search.mode == "payment"
                        else "La busqueda vencio. Pulsa Buscar para intentar otra vez."
                    ),
                )
                return
            if search.mode == "credentials" and search.order_id:
                if not _mutation_user_authorized(config, chat, sender):
                    telegram.send_message(
                        chat_id,
                        "La contrasena solo se puede corregir por el operador autorizado "
                        "desde un chat privado.",
                    )
                    return
                if not 1 <= len(text) <= 200:
                    search.expires_at = time.monotonic() + CONVERSATION_TTL_SECONDS
                    telegram.send_message(
                        chat_id,
                        "La contrasena debe tener entre 1 y 200 caracteres. Intenta otra vez.",
                    )
                    _delete_message_safe(telegram, chat_id, message.get("message_id"))
                    return
                search_conversations.pop(chat_id, None)
                try:
                    _request_credentials_change(
                        chat_id,
                        search.order_id,
                        text,
                        telegram,
                        admin_api,
                        pending_order_changes,
                        confirmation_lock,
                        return_subject=search.return_subject,
                    )
                finally:
                    _delete_message_safe(telegram, chat_id, message.get("message_id"))
                return
            if search.mode == "payment" and search.order_id:
                search_conversations.pop(chat_id, None)
                _request_payment_change(
                    chat_id,
                    f"{search.order_id} {text}",
                    telegram,
                    admin_api,
                    pending_order_changes,
                    confirmation_lock,
                    return_subject=search.return_subject,
                )
                return
            search_conversations.pop(chat_id, None)
            _send_search_results(chat_id, text, telegram, admin_api)
            return
        new_client = new_client_conversations.get(chat_id)
        password_message = new_client is not None and new_client.step == 2
        if _process_new_client_message(
            chat_id,
            text,
            telegram,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        ):
            if password_message:
                message_id = message.get("message_id")
                if isinstance(message_id, int):
                    try:
                        telegram.delete_message(chat_id, message_id)
                    except TelegramControlError:
                        logger.warning("Could not delete Telegram password input message.")
            return
        if _process_rules_conversation_message(
            chat_id,
            text,
            telegram,
            rules_conversations,
            pending_order_changes,
            confirmation_lock,
        ):
            return
    command, arguments = _command_parts(text)
    if command is None:
        telegram.send_message(
            chat_id,
            "No entendi ese mensaje. Usa /menu para elegir una opcion o /buscar TEXTO.",
            reply_markup=_main_menu_markup(),
        )
        return
    mutation = command in MUTATING_COMMANDS
    if mutation and not _mutation_user_authorized(config, chat, sender):
        _record_audit_safe(
            admin_api=admin_api,
            actor=_telegram_actor(chat_id, user_id),
            action=command,
            status="denied",
            detail="Mutation requires an authorized user in a private chat.",
        )
        telegram.send_message(
            chat_id,
            "Por seguridad, esta accion solo se permite al operador autorizado "
            "desde un chat privado.",
        )
        return
    if not rate_limiter.allow(chat_id, mutation=mutation):
        _record_audit_safe(
            admin_api=admin_api,
            actor=_telegram_actor(chat_id),
            action=command,
            status="rate_limited",
            target_id=(
                _audit_target(arguments) if command in ORDER_TARGET_COMMANDS else None
            ),
        )
        telegram.send_message(
            chat_id,
            "Recibi demasiadas solicitudes seguidas. Espera un minuto y vuelve a intentar.",
        )
        return
    audit_target = _audit_target(arguments) if command in ORDER_TARGET_COMMANDS else None
    _record_audit_safe(
        admin_api=admin_api,
        actor=_telegram_actor(chat_id, user_id),
        action=command,
        status="accepted",
        target_type="service_order" if audit_target else None,
        target_id=audit_target,
    )
    if command in {"menu", "start"}:
        _send_main_menu(chat_id, telegram, admin_api)
        return
    if command in {"ayuda", "help"}:
        telegram.send_message(chat_id, HELP_TEXT, reply_markup=_main_menu_markup())
        return
    if command == "cancelar":
        removed = _cancel_chat_confirmations(chat_id, pending_confirmations, confirmation_lock)
        order_removed = _cancel_chat_order_state(
            chat_id,
            pending_order_changes,
            rules_conversations,
            confirmation_lock,
        )
        with confirmation_lock:
            client_removed = new_client_conversations.pop(chat_id, None) is not None
            client_removed = _cancel_pending_client_creation_unlocked(
                chat_id, pending_client_creations
            ) or client_removed
            search_removed = search_conversations.pop(chat_id, None) is not None
            captcha_removed = captcha_conversations.pop(chat_id, None) is not None
        response = (
            "Operacion pendiente cancelada."
            if removed
            or order_removed
            or client_removed
            or search_removed
            or captcha_removed
            else "No hay una operacion guiada activa."
        )
        telegram.send_message(chat_id, response)
        return
    if command == "estado":
        _send_worker_panel(chat_id, telegram, admin_api)
        return
    if command == "oportunidad":
        if arguments:
            telegram.send_message(chat_id, "Uso: /oportunidad")
            return
        _send_opportunity_panel(chat_id, telegram, admin_api)
        return
    if command == "clientes":
        _send_clients(chat_id, arguments, telegram, admin_api)
        return
    if command == "pendientes":
        _send_pending_attention(chat_id, arguments, telegram, admin_api)
        return
    if command == "cola":
        _send_queue(chat_id, arguments, telegram, admin_api)
        return
    if command == "cobros":
        _send_pending_payments(chat_id, arguments, telegram, admin_api)
        return
    if command == "buscar":
        _send_search_results(chat_id, arguments, telegram, admin_api)
        return
    if command == "resumen":
        _send_daily_summary(chat_id, telegram, admin_api)
        return
    if command == "captchas":
        try:
            captcha_enabled = bool(admin_api.get_health().get("captcha_shadow_enabled"))
        except TelegramControlError:
            captcha_enabled = False
        if not captcha_enabled:
            telegram.send_message(
                chat_id,
                "El etiquetado CAPTCHA no esta activo en este momento.",
                reply_markup=_main_menu_markup(),
            )
            return
        search_conversations.pop(chat_id, None)
        _cancel_chat_client_state(
            chat_id,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        )
        _cancel_chat_order_state(
            chat_id,
            pending_order_changes,
            rules_conversations,
            confirmation_lock,
        )
        _start_captcha_review(chat_id, telegram, admin_api, captcha_conversations)
        return
    if command in {"cliente", "reglas"}:
        _send_order_query(chat_id, command, arguments, telegram, admin_api)
        return
    if command == "cliente_nuevo":
        search_conversations.pop(chat_id, None)
        captcha_conversations.pop(chat_id, None)
        _cancel_chat_order_state(
            chat_id,
            pending_order_changes,
            rules_conversations,
            confirmation_lock,
        )
        _start_new_client_conversation(
            chat_id,
            arguments,
            telegram,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        )
        return
    if command == "prioridad":
        _request_priority_change(
            chat_id,
            arguments,
            telegram,
            admin_api,
            pending_order_changes,
            confirmation_lock,
        )
        return
    if command == "pago":
        _request_payment_change(
            chat_id,
            arguments,
            telegram,
            admin_api,
            pending_order_changes,
            confirmation_lock,
        )
        return
    if command == "reglas_editar":
        search_conversations.pop(chat_id, None)
        captcha_conversations.pop(chat_id, None)
        _cancel_chat_client_state(
            chat_id,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        )
        _start_rules_conversation(
            chat_id,
            arguments,
            telegram,
            admin_api,
            rules_conversations,
            pending_order_changes,
            confirmation_lock,
        )
        return
    if command == "ultimos_errores":
        _send_recent_errors(chat_id, telegram, admin_api)
        return
    if command in {"pausar", "reanudar", "reiniciar"}:
        if arguments:
            telegram.send_message(chat_id, f"Uso: /{command}")
            return
        worker_command = {
            "pausar": "pause",
            "reanudar": "resume",
            "reiniciar": "restart",
        }[command]
        _request_worker_confirmation(
            chat_id,
            worker_command,
            telegram,
            pending_confirmations,
            confirmation_lock,
        )
        return
    telegram.send_message(chat_id, "Comando no reconocido. Usa /ayuda.")
